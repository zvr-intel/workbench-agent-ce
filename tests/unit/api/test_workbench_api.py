# tests/unit/api/test_workbench_api.py

# Import from the package structure
from workbench_agent.api.services.report_service import ReportService

# --- Test Cases ---
# Note: WorkbenchClient initialization and composition tests have been removed
# as they conflict with integration test patches. These scenarios are better
# tested in integration tests which provide more realistic coverage.


# --- Test API Class Constants ---
def test_api_report_type_constants():
    """Test that report type sets match ``REPORT_DEFS``."""
    assert isinstance(ReportService.ASYNC_REPORT_TYPES, set)
    scan_types = ReportService.report_types_for_scope("scan")
    project_types = ReportService.report_types_for_scope("project")
    assert isinstance(scan_types, set)
    assert isinstance(project_types, set)

    assert "xlsx" in ReportService.ASYNC_REPORT_TYPES
    assert "spdx" in project_types
    assert "html" in scan_types
