"""
UploadService - Handles upload business logic and orchestration.

This service provides:
- Upload scan targets (archives or hashes)
- Upload dependency analysis results
- Upload SBOM files

Example:
    >>> upload_service = UploadService(uploads_client)
    >>> upload_service.upload_scan_target(scan_code, "/path/to/source.zip")
    >>> upload_service.upload_da_results(scan_code, "results.json")
"""

import base64
import logging
import os

from workbench_agent.exceptions import FileSystemError

logger = logging.getLogger("workbench-agent")


class UploadService:
    """
    Service for upload operations.

    This service handles business logic for:
    - Validating the input is an existing file
    - Building appropriate headers based on upload type
    - Deciding upload strategy (chunked vs standard) based on file size
    - Delegating HTTP transport to the UploadsClient

    Architecture:
    - Service layer: Validate input, Build Headers, Decide Upload Strategy
    - Client layer: Raw HTTP API calls (standard and chunked implementations)

    Example:
        >>> upload_service = UploadService(uploads_client)
        >>>
        >>> # Upload a pre-built scan target archive or hash file
        >>> upload_service.upload_scan_target(
        ...     scan_code="scan_code",
        ...     path="/path/to/source.zip"
        ... )
        >>>
        >>> # Upload dependency analysis results
        >>> upload_service.upload_da_results(
        ...     scan_code="scan_code",
        ...     path="/path/to/da_results.json"
        ... )
        >>>
        >>> # Upload SBOM file
        >>> upload_service.upload_sbom_file(
        ...     scan_code="scan_code",
        ...     path="/path/to/sbom.json"
        ... )
    """

    # Upload strategy constants (business logic)
    # Files larger than this threshold use chunked upload (matches typical
    # PHP post_max_size / NGINX client_max_body_size, e.g. 8MB).
    CHUNKED_UPLOAD_THRESHOLD = 7 * 1024 * 1024  # 7MB

    def __init__(self, uploads_client):
        """
        Initialize UploadService.

        Args:
            uploads_client: UploadsClient instance for raw API calls
        """
        self._uploads = uploads_client
        logger.debug("UploadService initialized")

    # ===== PUBLIC API =====

    def upload_scan_target(self, scan_code: str, path: str) -> None:
        """
        Upload a scan target file (e.g. zip archive or hash file) to a scan.

        This method accepts a file. Callers are responsible
        for data preparation (e.g. compressing a directory
        into a zip or generating a hashes via the FossID Toolbox).

        This method handles:
        - Validating the file exists
        - Building appropriate headers
        - Delegating to UploadsClient for HTTP operations

        Args:
            scan_code: Code of the scan to upload to
            path: Path to the file to upload

        Raises:
            FileSystemError: If path is not an existing file
            ApiError: If upload fails
            NetworkError: If there are network issues

        Example:
            >>> upload_service.upload_scan_target(
            ...     "SCAN123", "/path/to/source.zip"
            ... )
        """
        if not os.path.exists(path) or not os.path.isfile(path):
            raise FileSystemError(
                f"Scan target file does not exist: {path}"
            )

        upload_basename = os.path.basename(path)
        name_b64 = base64.b64encode(upload_basename.encode()).decode(
            "utf-8"
        )
        scan_code_b64 = base64.b64encode(scan_code.encode()).decode(
            "utf-8"
        )

        headers = {
            "FOSSID-SCAN-CODE": scan_code_b64,
            "FOSSID-FILE-NAME": name_b64,
            "Accept": "*/*",
        }

        # Decide upload strategy based on file size (business logic)
        file_size = os.path.getsize(path)
        if file_size > self.CHUNKED_UPLOAD_THRESHOLD:
            logger.debug(
                f"File size ({file_size / (1024 * 1024):.2f} MB) exceeds "
                f"({self.CHUNKED_UPLOAD_THRESHOLD / (1024 * 1024):.0f} MB) "
                f"threshold; using chunked upload."
            )
            self._uploads.upload_file_chunked(path, headers)
        else:
            logger.debug("Using standard (non-chunked) upload.")
            self._uploads.upload_file_standard(path, headers)

    def upload_da_results(self, scan_code: str, path: str) -> None:
        """
        Upload a dependency analysis result file to a scan.

        This method handles:
        - Validating file existence
        - Building appropriate headers (including FOSSID-UPLOAD-TYPE)
        - Delegating to UploadsClient for HTTP operations

        Args:
            scan_code: Code of the scan to upload to
            path: Path to the dependency analysis results file

        Raises:
            FileSystemError: If file doesn't exist
            ApiError: If upload fails
            NetworkError: If there are network issues

        Example:
            >>> upload_service.upload_da_results(
            ...     "SCAN123",
            ...     "/path/to/da_results.json"
            ... )
        """
        if not os.path.exists(path) or not os.path.isfile(path):
            raise FileSystemError(
                f"Dependency analysis results file does not exist: {path}"
            )

        upload_basename = os.path.basename(path)
        name_b64 = base64.b64encode(upload_basename.encode()).decode(
            "utf-8"
        )
        scan_code_b64 = base64.b64encode(scan_code.encode()).decode(
            "utf-8"
        )

        headers = {
            "FOSSID-SCAN-CODE": scan_code_b64,
            "FOSSID-FILE-NAME": name_b64,
            "FOSSID-UPLOAD-TYPE": "dependency_analysis",
            "Accept": "*/*",
        }

        # Decide upload strategy based on file size (business logic)
        file_size = os.path.getsize(path)
        if file_size > self.CHUNKED_UPLOAD_THRESHOLD:
            logger.debug(
                f"File size ({file_size / (1024 * 1024):.2f} MB) exceeds "
                f"({self.CHUNKED_UPLOAD_THRESHOLD / (1024 * 1024):.0f} MB) "
                f"threshold; using chunked upload."
            )
            self._uploads.upload_file_chunked(path, headers)
        else:
            logger.debug("Using standard (non-chunked) upload.")
            self._uploads.upload_file_standard(path, headers)

    def upload_sbom_file(self, scan_code: str, path: str) -> None:
        """
        Upload an SBOM file to a scan.

        This method handles:
        - Validating file existence
        - Building appropriate headers
        - Delegating to UploadsClient for HTTP operations

        Args:
            scan_code: Code of the scan to upload to
            path: Path to the SBOM file to upload

        Raises:
            FileSystemError: If file doesn't exist
            ApiError: If upload fails
            NetworkError: If there are network issues

        Example:
            >>> upload_service.upload_sbom_file(
            ...     "SCAN123",
            ...     "/path/to/sbom.json"
            ... )
        """
        if not os.path.exists(path) or not os.path.isfile(path):
            raise FileSystemError(f"SBOM file does not exist: {path}")

        upload_basename = os.path.basename(path)
        name_b64 = base64.b64encode(upload_basename.encode()).decode(
            "utf-8"
        )
        scan_code_b64 = base64.b64encode(scan_code.encode()).decode(
            "utf-8"
        )

        headers = {
            "FOSSID-SCAN-CODE": scan_code_b64,
            "FOSSID-FILE-NAME": name_b64,
            "Accept": "*/*",
        }

        # Decide upload strategy based on file size (business logic)
        file_size = os.path.getsize(path)
        if file_size > self.CHUNKED_UPLOAD_THRESHOLD:
            logger.debug(
                f"File size ({file_size / (1024 * 1024):.2f} MB) exceeds "
                f"({self.CHUNKED_UPLOAD_THRESHOLD / (1024 * 1024):.0f} MB) "
                f"threshold; using chunked upload."
            )
            self._uploads.upload_file_chunked(path, headers)
        else:
            logger.debug("Using standard (non-chunked) upload.")
            self._uploads.upload_file_standard(path, headers)
