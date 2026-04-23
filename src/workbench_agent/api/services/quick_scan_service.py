"""
QuickScanService - Handler-facing wrapper for quick file scan API calls.
"""

import logging
from typing import TYPE_CHECKING, Any, Dict, List

if TYPE_CHECKING:
    from workbench_agent.api.clients.quickscan_api import QuickScanClient

logger = logging.getLogger("workbench-agent")


class QuickScanService:
    """Thin orchestration layer over ``QuickScanClient``."""

    def __init__(self, quick_scan_client: "QuickScanClient") -> None:
        self._quick_scan = quick_scan_client
        logger.debug("QuickScanService initialized")

    def scan_one_file(
        self, file_content_b64: str, limit: int = 1, sensitivity: int = 10
    ) -> List[Dict[str, Any]]:
        """Run a quick scan on base64-encoded file content."""
        return self._quick_scan.scan_one_file(
            file_content_b64,
            limit=limit,
            sensitivity=sensitivity,
        )
