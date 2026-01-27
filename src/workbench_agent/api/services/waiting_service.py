"""
WaitingService - Deprecated thin wrapper around StatusCheckService.

DEPRECATED: This service is deprecated. Use StatusCheckService with wait=True instead.

This service is maintained for backward compatibility during the transition.
All methods are thin wrappers that call StatusCheckService with wait=True.

Migration:
    OLD: client.waiting.wait_for_scan(scan_code, max_tries=360, wait_interval=10)
    NEW: client.status_check.check_scan_status(scan_code, wait=True,
                                                 wait_retry_count=360,
                                                 wait_retry_interval=10)
"""

import logging
import warnings

from workbench_agent.api.utils.process_waiter import (
    StatusResult,
    WaitResult,  # Backward compat alias
)

logger = logging.getLogger("workbench-agent")


class WaitingService:
    """
    DEPRECATED: Thin wrapper around StatusCheckService for backward compatibility.

    This service is deprecated. Use StatusCheckService with wait=True instead.

    All methods emit deprecation warnings and delegate to StatusCheckService.

    Example (deprecated):
        >>> service = WaitingService(status_check_service)
        >>> result = service.wait_for_scan("scan_123")  # Deprecated

    Example (recommended):
        >>> status_check = StatusCheckService(scans_client, projects_client)
        >>> result = status_check.check_scan_status("scan_123", wait=True)
    """

    def __init__(self, status_check_service):
        """
        Initialize WaitingService.

        Args:
            status_check_service: StatusCheckService for status checking
        """
        self._status_check = status_check_service
        logger.debug("WaitingService initialized (deprecated wrapper)")

    # =========================================================================
    # SCAN OPERATIONS (4 methods) - DEPRECATED WRAPPERS
    # =========================================================================

    def wait_for_scan(
        self,
        scan_code: str,
        max_tries: int = 360,
        wait_interval: int = 10,
        should_track_files: bool = False,
    ) -> StatusResult:
        """
        DEPRECATED: Wait for a KB scan operation to complete.

        Use status_check.check_scan_status(scan_code, wait=True) instead.

        Args:
            scan_code: Code of the scan to check
            max_tries: Maximum attempts before timeout (default: 360)
            wait_interval: Seconds between attempts (default: 10)
            should_track_files: Show detailed file progress (default: False)

        Returns:
            StatusResult: Result with final status and duration
        """
        warnings.warn(
            "client.waiting.wait_for_scan() is deprecated. "
            "Use client.status_check.check_scan_status(..., wait=True) "
            "instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        return self._status_check.check_scan_status(
            scan_code,
            wait=True,
            wait_retry_count=max_tries,
            wait_retry_interval=wait_interval,
            should_track_files=should_track_files,
        )

    def wait_for_da(
        self, scan_code: str, max_tries: int = 360, wait_interval: int = 10
    ) -> StatusResult:
        """
        DEPRECATED: Wait for dependency analysis to complete.

        Use status_check.check_dependency_analysis_status(scan_code, wait=True)
        instead.

        Args:
            scan_code: Code of the scan to check
            max_tries: Maximum attempts before timeout (default: 360)
            wait_interval: Seconds between attempts (default: 10)

        Returns:
            StatusResult: Result with final status and duration
        """
        warnings.warn(
            "client.waiting.wait_for_da() is deprecated. "
            "Use client.status_check.check_dependency_analysis_status(..., "
            "wait=True) instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        return self._status_check.check_dependency_analysis_status(
            scan_code,
            wait=True,
            wait_retry_count=max_tries,
            wait_retry_interval=wait_interval,
        )

    def wait_for_extract_archives(
        self, scan_code: str, max_tries: int = 360, wait_interval: int = 10
    ) -> StatusResult:
        """
        DEPRECATED: Wait for archive extraction to complete.

        Use status_check.check_extract_archives_status(scan_code, wait=True)
        instead.

        Args:
            scan_code: Code of the scan to check
            max_tries: Maximum attempts before timeout (default: 360)
            wait_interval: Seconds between attempts (default: 10)

        Returns:
            StatusResult: Result with final status and duration
        """
        warnings.warn(
            "client.waiting.wait_for_extract_archives() is deprecated. "
            "Use client.status_check.check_extract_archives_status(..., "
            "wait=True) instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        return self._status_check.check_extract_archives_status(
            scan_code,
            wait=True,
            wait_retry_count=max_tries,
            wait_retry_interval=wait_interval,
        )

    def wait_for_report_import(
        self, scan_code: str, max_tries: int = 360, wait_interval: int = 10
    ) -> StatusResult:
        """
        DEPRECATED: Wait for SBOM/SPDX report import to complete.

        Use status_check.check_report_import_status(scan_code, wait=True)
        instead.

        Args:
            scan_code: Code of the scan to check
            max_tries: Maximum attempts before timeout (default: 360)
            wait_interval: Seconds between attempts (default: 10)

        Returns:
            StatusResult: Result with final status and duration
        """
        warnings.warn(
            "client.waiting.wait_for_report_import() is deprecated. "
            "Use client.status_check.check_report_import_status(..., "
            "wait=True) instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        return self._status_check.check_report_import_status(
            scan_code,
            wait=True,
            wait_retry_count=max_tries,
            wait_retry_interval=wait_interval,
        )

    # =========================================================================
    # REPORT OPERATIONS (2 methods) - DEPRECATED WRAPPERS
    # =========================================================================

    def wait_for_scan_report_completion(
        self,
        scan_code: str,
        process_id: int,
        max_tries: int = 360,
        wait_interval: int = 10,
    ) -> StatusResult:
        """
        DEPRECATED: Wait for scan report generation to complete.

        Use status_check.check_scan_report_status(scan_code, process_id,
        wait=True) instead.

        Args:
            scan_code: Code of the scan
            process_id: Process queue ID from report generation
            max_tries: Maximum attempts before timeout (default: 360)
            wait_interval: Seconds between attempts (default: 10)

        Returns:
            StatusResult: Result with final status and duration
        """
        warnings.warn(
            "client.waiting.wait_for_scan_report_completion() is deprecated. "
            "Use client.status_check.check_scan_report_status(..., wait=True) "
            "instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        return self._status_check.check_scan_report_status(
            scan_code,
            process_id,
            wait=True,
            wait_retry_count=max_tries,
            wait_retry_interval=wait_interval,
        )

    def wait_for_project_report_completion(
        self,
        project_code: str,
        process_id: int,
        max_tries: int = 360,
        wait_interval: int = 10,
    ) -> StatusResult:
        """
        DEPRECATED: Wait for project report generation to complete.

        Use status_check.check_project_report_status(process_id, project_code,
        wait=True) instead.

        Args:
            project_code: Code of the project
            process_id: Process queue ID from report generation
            max_tries: Maximum attempts before timeout (default: 360)
            wait_interval: Seconds between attempts (default: 10)

        Returns:
            StatusResult: Result with final status and duration
        """
        warnings.warn(
            "client.waiting.wait_for_project_report_completion() is "
            "deprecated. Use client.status_check.check_project_report_status"
            "(..., wait=True) instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        return self._status_check.check_project_report_status(
            process_id,
            project_code,
            wait=True,
            wait_retry_count=max_tries,
            wait_retry_interval=wait_interval,
        )

    # =========================================================================
    # GIT OPERATIONS (1 method) - DEPRECATED WRAPPER
    # =========================================================================

    def wait_for_git_clone(
        self, scan_code: str, max_tries: int = 360, wait_interval: int = 10
    ) -> StatusResult:
        """
        DEPRECATED: Wait for git clone operation to complete.

        Use status_check.check_git_clone_status(scan_code, wait=True) instead.

        Args:
            scan_code: Code of the scan
            max_tries: Maximum attempts before timeout (default: 360)
            wait_interval: Seconds between attempts (default: 10)

        Returns:
            StatusResult: Result with final status and duration
        """
        warnings.warn(
            "client.waiting.wait_for_git_clone() is deprecated. "
            "Use client.status_check.check_git_clone_status(..., wait=True) "
            "instead.",
            DeprecationWarning,
            stacklevel=2,
        )

        return self._status_check.check_git_clone_status(
            scan_code,
            wait=True,
            wait_retry_count=max_tries,
            wait_retry_interval=wait_interval,
        )

