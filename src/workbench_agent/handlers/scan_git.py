# workbench_agent/handlers/scan_git.py

import argparse
import logging
from typing import TYPE_CHECKING

from workbench_agent.api.exceptions import (
    ProcessError,
    ProcessTimeoutError,
)
from workbench_agent.exceptions import WorkbenchAgentError
from workbench_agent.utilities.error_handling import handler_error_wrapper
from workbench_agent.utilities.post_scan_summary import print_scan_summary
from workbench_agent.utilities.pre_flight_checks import (
    scan_git_pre_flight_check,
)
from workbench_agent.utilities.scan_workflows import determine_scans_to_run

if TYPE_CHECKING:
    from workbench_agent.api import WorkbenchClient

logger = logging.getLogger("workbench-agent")


@handler_error_wrapper
def handle_scan_git(
    client: "WorkbenchClient", params: argparse.Namespace
) -> bool:
    """
    Handler for the 'scan-git' command.

    This handler performs a complete Git-based scanning workflow:
    1. Validates ID reuse source (if specified)
    2. Resolves/creates project and scan
    3. Ensures scan is idle
    4. Clones Git repository
    5. Removes .git directory
    6. Runs KB scan and/or dependency analysis
    7. Displays results

    Args:
        client: The Workbench API client instance
        params: Command line parameters including:
            - project_name: Name of the project
            - scan_name: Name of the scan
            - git_url: Git repository URL
            - git_branch/git_tag/git_commit: Git reference
            - Various scan configuration options

    Returns:
        bool: True if the operation completed successfully

    Raises:
        WorkbenchAgentError: If Git clone or scan fail
        ProcessTimeoutError: If processes timeout
        ProcessError: If processes fail
    """
    print(f"\n--- Running {params.command.upper()} Command ---")

    # Initialize timing dictionary
    durations = {
        "kb_scan": 0.0,
        "dependency_analysis": 0.0,
        "git_clone": 0.0,
    }

    # ID reuse validation happens automatically in the service layer

    # Resolve project and scan (find or create)
    print("\n--- Project and Scan Checks ---")
    print("Checking target Project and Scan...")
    _, scan_code, scan_is_new = client.resolver.resolve_project_and_scan(
        project_name=params.project_name,
        scan_name=params.scan_name,
        params=params,
    )

    print("\n--- Repo Clone & Scan Prep ---")

    # Ensure scan is idle before triggering Git clone
    scan_git_pre_flight_check(client, scan_code, scan_is_new, params)

    # Trigger Git clone
    git_ref_type = (
        "tag"
        if params.git_tag
        else ("commit" if params.git_commit else "branch")
    )
    git_ref_value = (
        params.git_tag or params.git_commit or params.git_branch
    )
    print(f"\nCloning the repository's {git_ref_value} {git_ref_type}.")

    # Download content from Git
    try:
        client.scans.download_content_from_git(scan_code)
        git_clone_result = client.status_check.check_git_clone_status(
            scan_code,
            wait=True,
            wait_retry_count=params.scan_number_of_tries,
            wait_retry_interval=3,  # Git clone typically finishes quickly
        )
        # Store git clone duration
        durations["git_clone"] = git_clone_result.duration or 0.0
        print("Git Clone Completed.")
    except Exception as e:
        logger.error(
            f"Failed to clone Git repository for '{scan_code}': {e}",
            exc_info=True,
        )
        raise WorkbenchAgentError(
            f"Failed to clone Git repository: {e}",
            details={"error": str(e)},
        ) from e

    # Remove .git directory before starting scan
    print("\nRemoving .git directory to optimize scan...")
    try:
        if client.scans.remove_uploaded_content(scan_code, ".git/"):
            print("Successfully removed .git directory.")
    except Exception as e:
        logger.warning(
            f"Error removing .git directory: {e}. "
            f"Continuing with scan..."
        )
        print(
            f"Warning: Error removing .git directory: {e}. "
            f"Continuing with scan..."
        )

    print("\n--- Scan Operations ---")
    # Determine which scan operations to run
    scan_operations = determine_scans_to_run(params)

    # Run KB Scan
    scan_completed = False
    da_completed = False

    try:
        # Handle dependency analysis only mode
        if (
            not scan_operations["run_kb_scan"]
            and scan_operations["run_dependency_analysis"]
        ):
            print(
                "Starting Dependency Analysis only (skipping KB scan)..."
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
            try:
                da_result = client.status_check.check_dependency_analysis_status(
                    scan_code,
                    wait=True,
                    wait_retry_count=params.scan_number_of_tries,
                    wait_retry_interval=params.scan_wait_time,
                )

                # Store the duration
                durations["dependency_analysis"] = da_result.duration or 0.0
                da_completed = True

                # Mark scan as completed for result processing
                scan_completed = True

                # Print operation summary
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

            except Exception as e:
                logger.error(
                    f"Error waiting for dependency analysis: {e}",
                    exc_info=True,
                )
                print(f"\nError: Dependency analysis failed: {e}")
                return False

        # Start the KB scan (only if run_kb_scan is True)
        if scan_operations["run_kb_scan"]:
            print("Starting KB Scan...")

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

            # Check if no-wait mode is enabled
            if getattr(params, "no_wait", False):
                print("\nKB Scan started successfully.")
                if scan_operations["run_dependency_analysis"]:
                    print(
                        "Dependency Analysis will automatically start "
                        "after scan completion."
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

                print(
                    f"\nWaiting for {', '.join(process_types_to_wait)} "
                    f"to complete..."
                )

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
                    scan_completed = True

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
                    scan_completed = False
                    da_completed = False

    except ProcessTimeoutError:
        scan_completed = False
        raise
    except ProcessError:
        scan_completed = False
        raise
    except Exception as e:
        scan_completed = False
        logger.error(
            f"Error during KB scan for '{scan_code}': {e}",
            exc_info=True,
        )
        raise WorkbenchAgentError(
            f"Error during KB scan: {e}", details={"error": str(e)}
        ) from e

    # Process completed operations
    if scan_completed:
        # Print operation summary
        scan_operations["da_completed"] = da_completed
        print_scan_summary(
            client,
            params,
            scan_code,
            durations,
            show_summary=getattr(params, "show_summary", False),
            scan_operations=scan_operations,
        )

    return scan_completed or da_completed
