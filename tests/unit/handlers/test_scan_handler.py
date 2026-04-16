"""Tests for scan handler -- incremental upload behavior."""

import argparse
from unittest.mock import MagicMock, patch

import pytest

from workbench_agent.handlers.scan import handle_scan


@pytest.fixture
def base_params():
    ns = argparse.Namespace()
    ns.command = "scan"
    ns.project_name = "TestProject"
    ns.scan_name = "TestScan"
    ns.path = "/tmp/src"
    ns.incremental_upload = False
    ns.recursively_extract_archives = True
    ns.jar_file_extraction = False
    ns.scan_number_of_tries = 10
    return ns


@pytest.fixture
def mock_client():
    client = MagicMock()
    client.resolver.resolve_project_and_scan.return_value = (
        "proj_code",
        "scan_code",
        False,
    )
    client.scan_operations.start_archive_extraction.return_value = False
    return client


class TestScanHandlerClearBehavior:
    """Tests for the content-clearing step gated by --incremental-upload."""

    @patch(
        "workbench_agent.handlers.scan.execute_scan_workflow",
        return_value=True,
    )
    @patch("workbench_agent.handlers.scan.scan_pre_flight_check")
    def test_existing_scan_clears_content_by_default(
        self, _mock_preflight, _mock_workflow, mock_client, base_params
    ):
        """Default behavior: existing scan content is cleared before upload."""
        handle_scan(mock_client, base_params)

        mock_client.scans.remove_uploaded_content.assert_called_once_with(
            "scan_code", ""
        )

    @patch(
        "workbench_agent.handlers.scan.execute_scan_workflow",
        return_value=True,
    )
    @patch("workbench_agent.handlers.scan.scan_pre_flight_check")
    def test_incremental_upload_skips_clear(
        self, _mock_preflight, _mock_workflow, mock_client, base_params
    ):
        """With --incremental-upload, existing content is NOT cleared."""
        base_params.incremental_upload = True

        handle_scan(mock_client, base_params)

        mock_client.scans.remove_uploaded_content.assert_not_called()

    @patch(
        "workbench_agent.handlers.scan.execute_scan_workflow",
        return_value=True,
    )
    @patch("workbench_agent.handlers.scan.scan_pre_flight_check")
    def test_incremental_upload_prints_message(
        self,
        _mock_preflight,
        _mock_workflow,
        mock_client,
        base_params,
        capsys,
    ):
        """Incremental upload on existing scan prints info message."""
        base_params.incremental_upload = True

        handle_scan(mock_client, base_params)

        captured = capsys.readouterr()
        assert (
            "Incremental upload: keeping existing scan content."
            in captured.out
        )

    @patch(
        "workbench_agent.handlers.scan.execute_scan_workflow",
        return_value=True,
    )
    @patch("workbench_agent.handlers.scan.scan_pre_flight_check")
    def test_new_scan_skips_clear_regardless_of_flag(
        self, _mock_preflight, _mock_workflow, mock_client, base_params
    ):
        """New scans never clear content, with or without the flag."""
        mock_client.resolver.resolve_project_and_scan.return_value = (
            "proj_code",
            "scan_code",
            True,
        )
        base_params.incremental_upload = True

        handle_scan(mock_client, base_params)

        mock_client.scans.remove_uploaded_content.assert_not_called()

    @patch(
        "workbench_agent.handlers.scan.execute_scan_workflow",
        return_value=True,
    )
    @patch("workbench_agent.handlers.scan.scan_pre_flight_check")
    def test_new_scan_without_flag_skips_clear(
        self, _mock_preflight, _mock_workflow, mock_client, base_params
    ):
        """New scans skip clearing even without --incremental-upload."""
        mock_client.resolver.resolve_project_and_scan.return_value = (
            "proj_code",
            "scan_code",
            True,
        )

        handle_scan(mock_client, base_params)

        mock_client.scans.remove_uploaded_content.assert_not_called()
