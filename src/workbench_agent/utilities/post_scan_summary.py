"""
Backward-compatibility re-exports.

All functionality has moved to
:mod:`workbench_agent.utilities.scan_workflows`.
"""

from workbench_agent.utilities.scan_workflows import (  # noqa: F401  # pylint: disable=unused-import
    _format_duration as format_duration,
    _print_scan_summary as print_scan_summary,
)
