# workbench_agent/handlers/download_reports.py

import argparse
import logging
import os
from typing import TYPE_CHECKING

from workbench_agent.api.exceptions import (
    ApiError,
    NetworkError,
    ProcessTimeoutError,
)
from workbench_agent.exceptions import FileSystemError, ValidationError
from workbench_agent.utilities.error_handling import handler_error_wrapper
from workbench_agent.utilities.post_report_summary import print_report_summary
from workbench_agent.utilities.pre_flight_checks import (
    download_reports_pre_flight_check,
)

if TYPE_CHECKING:
    from workbench_agent.api import WorkbenchClient

logger = logging.getLogger("workbench-agent")


def _resolve_report_types(client: "WorkbenchClient", params: argparse.Namespace):
    """
    Parse --report-type (ALL, CSV, or single) and apply version filtering for ALL.

    ALL: drop report types not supported by the connected Workbench (warn).
    Explicit: validate each type (raises if unsupported for this server).
    """
    if params.report_scope == "scan":
        full_set = client.reports.SCAN_REPORT_TYPES
    else:
        full_set = client.reports.PROJECT_REPORT_TYPES

    if params.report_type.upper() == "ALL":
        skipped = {
            rt
            for rt in full_set
            if not client.reports.is_report_type_supported(rt)
        }
        for rt in sorted(skipped):
            min_v = client.reports.MIN_VERSION_FOR_REPORT_TYPES.get(rt, "?")
            logger.warning(
                f"Skipping '{rt}' from ALL: requires Workbench >= {min_v}, "
                f"server is {client.get_workbench_version()}"
            )
        return full_set - skipped

    requested = {
        rt.strip().lower() for rt in params.report_type.split(",")
    }
    for rt in requested:
        client.reports.validate_report_type(rt, params.report_scope)
    return requested


@handler_error_wrapper
def handle_download_reports(
    client: "WorkbenchClient", params: argparse.Namespace
):
    """
    Handler for the 'download-reports' command.

    Downloads reports for a scan or project. Supports both synchronous and
    asynchronous report generation with multiple report formats.

    Args:
        client: The Workbench API client
        params: Command line parameters including:
            - report_scope: "scan" or "project"
            - report_type: Comma-separated list or "ALL"
            - report_save_path: Output directory
            - project_name: Project name (required for project scope)
            - scan_name: Scan name (required for scan scope)

    Returns:
        True if at least one report was successfully downloaded

    Raises:
        ValidationError: If parameters are invalid
        FileSystemError: If file operations fail
        ApiError: If API operations fail
    """
    print(f"\n--- Running {params.command.upper()} Command ---")

    report_types = _resolve_report_types(client, params)
    logger.debug(f"Resolved report types to download: {report_types}")

    # Create output directory if it doesn't exist
    output_dir = params.report_save_path
    if not os.path.exists(output_dir):
        print(f"Creating output directory: {output_dir}")
        os.makedirs(output_dir, exist_ok=True)

    # Note: Project/scan name requirements are validated at CLI layer (cli/validators.py)
    # Resolve project, scan
    scope_name = (
        params.scan_name
        if params.report_scope == "scan"
        else params.project_name
    )
    print(
        f"\nResolving "
        f"{'scan' if params.report_scope == 'scan' else 'project'} "
        f"'{scope_name}'..."
    )

    project_code = None
    scan_code = None

    if params.project_name:
        project_code = client.resolver.find_project(params.project_name)

    if params.report_scope == "scan":
        # If scan scope, we need a scan code
        if params.scan_name:
            # Try to resolve using project context first if provided
            if project_code and params.project_name:
                scan_code, _ = client.resolver.find_scan(
                    scan_name=params.scan_name,
                    project_name=params.project_name,
                    project_code=project_code,
                )
            else:
                # Try to resolve globally if project not provided
                scan_code, _ = client.resolver.find_scan(
                    scan_name=params.scan_name,
                    project_name=None,
                )
    # Note: project_code validation for project scope is done at CLI layer

    # Check scan completion status for scan-scope reports
    if params.report_scope == "scan" and scan_code:
        download_reports_pre_flight_check(client, scan_code, params)

    # Generate and download reports based on scope
    scope_label = "project" if params.report_scope == "project" else "scan"
    print(
        f"\nGenerating and downloading {len(report_types)} "
        f"{scope_label} report(s)..."
    )

    # Print the actual report types being downloaded
    for rt in sorted(report_types):
        print(f"- {rt}")

    # Type assertions for type checker (validated during resolution)
    if params.report_scope == "project":
        assert project_code is not None
    if params.report_scope == "scan":
        assert scan_code is not None

    # Track results for summary
    success_count = 0
    error_count = 0
    error_types = []

    # Process each report type sequentially
    for report_type in sorted(report_types):
        try:
            # Generate the report
            print(f"\nGenerating {report_type} report...")

            # Get the right name component for file naming
            name_component = (
                params.project_name
                if params.report_scope == "project"
                else params.scan_name
            )

            if report_type in client.reports.NOTICE_REPORT_TYPES:
                notice_api_type = client.reports.NOTICE_REPORT_TYPE_MAP[
                    report_type
                ]
                client.reports.generate_notice_extract(
                    scan_code, notice_api_type
                )
                max_tries = getattr(params, "scan_number_of_tries", 60)
                try:
                    print(
                        f"Waiting for {report_type} report generation to "
                        f"complete..."
                    )
                    client.reports.check_notice_extract_status(
                        scan_code,
                        notice_api_type,
                        wait=True,
                        wait_retry_count=max_tries,
                        wait_retry_interval=3,
                    )
                except ProcessTimeoutError as e:
                    logger.error(
                        f"Failed waiting for '{report_type}' notice extract: {e}"
                    )
                    error_count += 1
                    error_types.append(report_type)
                    continue
                except (ApiError, NetworkError) as e:
                    logger.error(
                        f"API error during '{report_type}' notice extract: {e}"
                    )
                    error_count += 1
                    error_types.append(report_type)
                    continue
                except Exception as e:
                    logger.error(
                        f"Unexpected error during '{report_type}' notice "
                        f"extract: {e}",
                        exc_info=True,
                    )
                    error_count += 1
                    error_types.append(report_type)
                    continue

                print(f"Downloading {report_type} report...")
                response = client.reports.download_notice_extract(
                    scan_code, notice_api_type
                )
                client.reports.save_report(
                    response,
                    output_dir,
                    name_component,
                    report_type,
                    scope=params.report_scope,
                )
                success_count += 1
                continue

            # Common parameters for standard report generation
            common_params = {
                "report_type": report_type,
            }

            # Add optional parameters if they were provided
            if params.selection_type is not None:
                common_params["selection_type"] = params.selection_type

            if params.selection_view is not None:
                common_params["selection_view"] = params.selection_view

            if params.disclaimer is not None:
                common_params["disclaimer"] = params.disclaimer

            # Include VEX data if requested (default is True)
            common_params["include_vex"] = params.include_vex

            # Check if this report type is synchronous or asynchronous
            is_async = client.reports.is_async_report_type(report_type)

            # Start report generation
            if is_async:
                # Asynchronous report generation
                if params.report_scope == "project":
                    process_id = client.reports.generate_project_report(
                        project_code, **common_params
                    )
                else:
                    process_id = client.reports.generate_scan_report(
                        scan_code, **common_params
                    )

                # Wait for report generation to complete
                try:
                    print(
                        f"Waiting for {report_type} report generation to "
                        f"complete..."
                    )

                    max_tries = getattr(params, "scan_number_of_tries", 60)
                    if params.report_scope == "project":
                        client.reports.check_project_report_status(
                            process_id=process_id,
                            project_code=project_code,
                            wait=True,
                            wait_retry_count=max_tries,
                            wait_retry_interval=3,
                        )
                    else:
                        client.reports.check_scan_report_status(
                            scan_code=scan_code,
                            process_id=process_id,
                            wait=True,
                            wait_retry_count=max_tries,
                            wait_retry_interval=3,
                        )
                except ProcessTimeoutError as e:
                    logger.error(
                        f"Failed waiting for '{report_type}' report "
                        f"(Process ID: {process_id}): {e}"
                    )
                    error_count += 1
                    error_types.append(report_type)
                    continue
                except (ApiError, NetworkError) as e:
                    logger.error(
                        f"API error during '{report_type}' report generation "
                        f"(Process ID: {process_id}): {e}"
                    )
                    error_count += 1
                    error_types.append(report_type)
                    continue
                except Exception as e:
                    logger.error(
                        f"Unexpected error during '{report_type}' report "
                        f"generation (Process ID: {process_id}): {e}",
                        exc_info=True,
                    )
                    error_count += 1
                    error_types.append(report_type)
                    continue

                # Download the generated report
                print(f"Downloading {report_type} report...")
                if params.report_scope == "project":
                    response = client.reports.download_project_report(
                        process_id
                    )
                else:
                    response = client.reports.download_scan_report(
                        process_id
                    )

            else:
                # Synchronous report generation (returns response directly)
                print(f"Downloading {report_type} report...")
                if params.report_scope == "project":
                    # Note: Project reports are typically async
                    response = client.reports.generate_project_report(
                        project_code, **common_params
                    )
                else:
                    response = client.reports.generate_scan_report(
                        scan_code, **common_params
                    )

            # Save the report content
            client.reports.save_report(
                response,
                output_dir,
                name_component,
                report_type,
                scope=params.report_scope,
            )
            success_count += 1

        except (
            ApiError,
            NetworkError,
            FileSystemError,
            ValidationError,
        ) as e:
            print(
                f"Error processing {report_type} report: "
                f"{getattr(e, 'message', str(e))}"
            )
            logger.error(
                f"Failed to generate/download {report_type} report: {e}",
                exc_info=True,
            )
            error_count += 1
            error_types.append(report_type)

    # Show report summary (includes Workbench link for scan-scope reports)
    print_report_summary(
        client,
        params,
        report_types,
        success_count,
        error_count,
        error_types,
        scan_code=scan_code,
        project_code=project_code,
        show_summary=getattr(params, "show_summary", False),
    )

    # Return True if at least one report was successfully downloaded
    return success_count > 0
