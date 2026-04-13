import argparse
import json
import logging
import os
import time
from typing import TYPE_CHECKING

from workbench_agent.exceptions import ValidationError
from workbench_agent.utilities.error_handling import handler_error_wrapper
from workbench_agent.utilities.post_scan_summary import (
    format_duration,
    print_scan_summary,
)
from workbench_agent.utilities.pre_flight_checks import (
    blind_scan_pre_flight_check,
)
from workbench_agent.utilities.scan_workflows import determine_scans_to_run
from workbench_agent.utilities.toolbox_wrapper import ToolboxWrapper

if TYPE_CHECKING:
    from workbench_agent.api import WorkbenchClient

logger = logging.getLogger("workbench-agent")


def cleanup_temp_file(file_path: str) -> bool:
    """
    Clean up a temporary file.

    Args:
        file_path: Path to the temporary file to delete

    Returns:
        bool: True if file was successfully deleted or doesn't need
             cleanup, False otherwise
    """
    if not file_path:
        # No file path provided, consider this a successful "no-op" cleanup
        return True

    try:
        if os.path.exists(file_path):
            os.remove(file_path)
            logger.debug(f"Cleaned up temporary file: {file_path}")
            return True
        else:
            # File doesn't exist, so it's effectively "cleaned up" already
            logger.debug(
                f"Temporary file already doesn't exist: {file_path}"
            )
            return True
    except Exception as e:
        logger.error(f"Failed to clean up temporary file {file_path}: {e}")
        return False


def validate_fossid_file(file_path: str) -> None:
    """
    Validate the schema of a pre-generated .fossid file.

    Each line must be a JSON object containing at minimum:
    - path (str): Relative file path
    - size (int): File size in bytes
    - hashes_ffm (list): Hash objects, each with format (int) and data (str)

    Args:
        file_path: Path to the .fossid file to validate

    Raises:
        ValidationError: If the file is empty or has invalid schema
    """
    try:
        with open(file_path, "r") as f:
            lines = f.readlines()
    except Exception as e:
        raise ValidationError(
            f"Failed to read .fossid file '{file_path}': {e}"
        ) from e

    if not lines or all(line.strip() == "" for line in lines):
        raise ValidationError(
            f"The .fossid file '{file_path}' is empty."
        )

    required_fields = {"path": str, "size": int, "hashes_ffm": list}

    for line_num, line in enumerate(lines, start=1):
        line = line.strip()
        if not line:
            continue

        try:
            entry = json.loads(line)
        except json.JSONDecodeError as e:
            raise ValidationError(
                f"Invalid JSON on line {line_num} of "
                f"'{file_path}': {e}"
            ) from e

        if not isinstance(entry, dict):
            raise ValidationError(
                f"Line {line_num} of '{file_path}' is not a JSON object."
            )

        for field, expected_type in required_fields.items():
            if field not in entry:
                raise ValidationError(
                    f"Line {line_num} of '{file_path}' is missing "
                    f"required field '{field}'."
                )
            if not isinstance(entry[field], expected_type):
                raise ValidationError(
                    f"Line {line_num} of '{file_path}': '{field}' must "
                    f"be {expected_type.__name__}."
                )

        for i, hash_entry in enumerate(entry["hashes_ffm"]):
            if not isinstance(hash_entry, dict):
                raise ValidationError(
                    f"Line {line_num} of '{file_path}': "
                    f"'hashes_ffm[{i}]' must be an object."
                )
            if "format" not in hash_entry or "data" not in hash_entry:
                raise ValidationError(
                    f"Line {line_num} of '{file_path}': "
                    f"'hashes_ffm[{i}]' must have 'format' and "
                    f"'data' fields."
                )

    non_empty = sum(1 for l in lines if l.strip())
    logger.info(
        f"Validated .fossid file '{file_path}': {non_empty} entries."
    )


@handler_error_wrapper
def handle_blind_scan(
    client: "WorkbenchClient", params: argparse.Namespace
) -> bool:
    """
    Handler for the 'blind-scan' command.

    Uses FossID Toolbox to generate file hashes, uploads the hash file,
    and then follows the same pattern as regular scan. This allows
    scanning without uploading source code to Workbench.

    Alternatively, accepts a pre-generated .fossid file directly,
    skipping the Toolbox hashing step entirely.

    Workflow:
    1. Validates parameters and detects input type
    2a. If .fossid file: validates file schema
    2b. If directory: validates Toolbox and generates hashes
    4. Resolves/creates project and scan in Workbench
    5. Uploads hash file to Workbench
    6. Runs requested scans
    7. Displays requested results
    8. Cleans up temporary hash file (only if generated)

    This order ensures local prerequisites (toolbox, hash generation) are
    validated before any API calls to Workbench, avoiding creation of
    resources if local validation fails.

    Args:
        client: The Workbench API client instance
        params: Command line parameters including:
            - path: Directory to hash, or pre-generated .fossid file
            - Various scan configuration options

    Returns:
        bool: True if the operation completed successfully

    Raises:
        ValidationError: If required parameters are invalid
        FileSystemError: If specified paths don't exist
        ProcessError: If CLI execution fails
    """
    print(f"\n--- Running {params.command.upper()} Command ---")

    # Initialize timing dictionary
    durations = {
        "hash_generation": 0.0,
        "kb_scan": 0.0,
        "dependency_analysis": 0.0,
    }

    # ===== STEP 1: Validate scan parameters =====
    # Note: Path existence is validated at CLI layer (cli/validators.py)
    is_pregenerated = (
        os.path.isfile(params.path)
        and params.path.endswith(".fossid")
    )

    if not is_pregenerated and not os.path.isdir(params.path):
        raise ValidationError(
            f"The provided path must be a directory to hash, or a "
            f"pre-generated .fossid file. Provided: {params.path}"
        )

    hash_file_path = None
    should_cleanup = False

    try:
        if is_pregenerated:
            print("\nValidating pre-generated .fossid file...")
            validate_fossid_file(params.path)
            hash_file_path = params.path
            print("Validation successful. Skipping hash generation.")
        else:
            # ===== STEP 2: Validate FossID Toolbox availability =====
            print("\nValidating FossID Toolbox...")
            toolbox_wrapper = ToolboxWrapper(
                toolbox_path=getattr(
                    params, "fossid_toolbox_path",
                    "/usr/bin/fossid-toolbox"
                ),
            )

            try:
                version = toolbox_wrapper.get_version()
                print(f"Using {version}")
            except Exception as e:
                logger.error(
                    f"FossID Toolbox validation failed: {e}"
                )
                raise ValidationError(
                    f"FossID Toolbox is not available or cannot be "
                    f"executed. Please ensure it is installed and "
                    f"accessible at the specified path. Error: {e}"
                ) from e

            # ===== STEP 3: Generate file hashes =====
            print("\nGenerating file hashes using FossID Toolbox...")
            hash_start_time = time.time()
            hash_file_path = toolbox_wrapper.generate_hashes(
                path=params.path,
                run_dependency_analysis=getattr(
                    params, "run_dependency_analysis", False
                ),
            )
            hash_duration = time.time() - hash_start_time
            durations["hash_generation"] = hash_duration
            print(
                f"Hash generation completed in "
                f"{format_duration(hash_duration)}."
            )
            should_cleanup = True

        # ===== STEP 4: Resolve/create project and scan in Workbench =====
        print("\n--- Project and Scan Checks ---")
        print("Checking target Project and Scan...")
        _, scan_code, scan_is_new = (
            client.resolver.resolve_project_and_scan(
                project_name=params.project_name,
                scan_name=params.scan_name,
                params=params,
            )
        )

        # Assert scan is idle before starting blind scan operations
        blind_scan_pre_flight_check(client, scan_code, scan_is_new, params)

        # Clear existing scan content (skip for new scans - they're empty)
        if not scan_is_new:
            print("\nClearing existing scan content...")
            try:
                client.scans.remove_uploaded_content(scan_code, "")
                print("Successfully cleared existing scan content.")
            except Exception as e:
                logger.warning(
                    f"Failed to clear existing scan content: {e}"
                )
                print(
                    f"Warning: Could not clear existing scan content: {e}"
                )
                print("Continuing with hash upload...")
        else:
            logger.debug("Skipping content clear - new scan is empty")

        # ===== STEP 5: Upload hash file to Workbench =====
        print("\nUploading hashes to Workbench...")
        client.upload_service.upload_scan_target(scan_code, hash_file_path)
        print("Hashes uploaded successfully!")

        # ===== STEP 6: Run scans =====
        # Determine which scan operations to run
        scan_operations = determine_scans_to_run(params)
        da_completed = False

        # Handle dependency analysis only mode
        if (
            not scan_operations["run_kb_scan"]
            and scan_operations["run_dependency_analysis"]
        ):
            print(
                "\nStarting Dependency Analysis only (skipping KB scan)..."
            )
            client.scan_operations.start_da_only(scan_code)

            # Handle no-wait mode
            if getattr(params, "no_wait", False):
                print("Dependency Analysis has been started.")
                print(
                    "\nExiting without waiting for completion "
                    "(--no-wait mode)."
                )
                print(
                    "You can check the status later using the "
                    "'show-results' command."
                )
                # Always show only link in no-wait mode (avoid stale data)
                scan_operations["da_completed"] = False
                print_scan_summary(
                    client,
                    params,
                    scan_code,
                    durations,
                    show_summary=False,
                    scan_operations=scan_operations,
                )
                return True

            # Wait for dependency analysis to complete
            print("\nWaiting for Dependency Analysis to complete...")
            da_result = client.status_check.check_dependency_analysis_status(
                scan_code,
                wait=True,
                wait_retry_count=params.scan_number_of_tries,
                wait_retry_interval=params.scan_wait_time,
            )
            durations["dependency_analysis"] = da_result.duration or 0.0
            da_completed = True

        # Start the KB scan (only if run_kb_scan is True)
        if scan_operations["run_kb_scan"]:
            print("\nStarting Scan Process...")

            # Resolve ID reuse parameters (if any)
            id_reuse_type, id_reuse_specific_code = (
                client.resolver.resolve_id_reuse(
                    id_reuse_any=getattr(
                        params, "reuse_any_identification", False
                    ),
                    id_reuse_my=getattr(
                        params, "reuse_my_identifications", False
                    ),
                    id_reuse_project_name=getattr(
                        params, "reuse_project_ids", None
                    ),
                    id_reuse_scan_name=getattr(
                        params, "reuse_scan_ids", None
                    ),
                    current_project_name=params.project_name,
                )
            )

            # Run scan with resolved ID reuse parameters
            client.scan_operations.start_scan(
                scan_code=scan_code,
                limit=params.limit,
                sensitivity=params.sensitivity,
                autoid_file_licenses=params.autoid_file_licenses,
                autoid_file_copyrights=params.autoid_file_copyrights,
                autoid_pending_ids=params.autoid_pending_ids,
                delta_scan=params.delta_scan,
                id_reuse_type=id_reuse_type,
                id_reuse_specific_code=id_reuse_specific_code,
                run_dependency_analysis=scan_operations[
                    "run_dependency_analysis"
                ],
                replace_existing_identifications=getattr(
                    params, "replace_existing_identifications", False
                ),
                scan_failed_only=getattr(
                    params, "scan_failed_only", False
                ),
                full_file_only=getattr(params, "full_file_only", False),
                advanced_match_scoring=getattr(
                    params, "advanced_match_scoring", True
                ),
                match_filtering_threshold=getattr(
                    params, "match_filtering_threshold", None
                ),
                scan_host=getattr(params, "scan_host", None),
            )

            # Check if we should wait for completion
            if getattr(params, "no_wait", False):
                print("\nKB Scan started successfully.")
                if scan_operations["run_dependency_analysis"]:
                    print(
                        "Dependency Analysis will start when KB scan "
                        "completes."
                    )
                print(
                    "\nExiting without waiting for completion "
                    "(--no-wait mode)."
                )
                # Always show only link in no-wait mode (avoid stale data)
                scan_operations["da_completed"] = False
                print_scan_summary(
                    client,
                    params,
                    scan_code,
                    durations,
                    show_summary=False,
                    scan_operations=scan_operations,
                )
                return True
            else:
                # Determine which processes to wait for
                process_types_to_wait = ["SCAN"]
                if scan_operations["run_dependency_analysis"]:
                    process_types_to_wait.append("DEPENDENCY_ANALYSIS")

                process_list = ", ".join(process_types_to_wait)
                print(f"\nWaiting for {process_list} to complete...")

                try:
                    # Wait for KB scan completion
                    kb_scan_result = client.status_check.check_scan_status(
                        scan_code,
                        wait=True,
                        wait_retry_count=params.scan_number_of_tries,
                        wait_retry_interval=params.scan_wait_time,
                        should_track_files=True,
                    )
                    durations["kb_scan"] = kb_scan_result.duration or 0.0

                    # Wait for dependency analysis if requested
                    if "DEPENDENCY_ANALYSIS" in process_types_to_wait:
                        print(
                            "\nWaiting for Dependency Analysis to complete..."
                        )
                        try:
                            da_result = client.status_check.check_dependency_analysis_status(
                                scan_code,
                                wait=True,
                                wait_retry_count=params.scan_number_of_tries,
                                wait_retry_interval=params.scan_wait_time,
                            )
                            durations["dependency_analysis"] = (
                                da_result.duration or 0.0
                            )
                            da_completed = True
                        except Exception as e:
                            logger.warning(
                                f"Error in dependency analysis: {e}"
                            )
                            print(
                                f"\nWarning: Error waiting for "
                                f"dependency analysis: {e}"
                            )
                            da_completed = False
                    else:
                        da_completed = False

                except Exception as e:
                    logger.error(
                        f"Error waiting for processes: {e}",
                        exc_info=True,
                    )
                    print(f"\nError: Process failed: {e}")
                    da_completed = False

        # Print standardized operation summary
        scan_operations["da_completed"] = da_completed
        print_scan_summary(
            client,
            params,
            scan_code,
            durations,
            show_summary=getattr(params, "show_summary", False),
            scan_operations=scan_operations,
        )

        return True

    finally:
        # ===== STEP 8: Clean up temporary hash file =====
        if should_cleanup and hash_file_path:
            cleanup_success = cleanup_temp_file(hash_file_path)
            if cleanup_success:
                logger.debug(
                    "Temporary hash file cleaned up successfully."
                )
            else:
                logger.warning("Failed to clean up temporary hash file.")
