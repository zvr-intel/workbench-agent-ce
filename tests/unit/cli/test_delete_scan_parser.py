"""Tests for delete-scan CLI parsing."""

from unittest.mock import patch

from workbench_agent.cli import parse_cmdline_args


def test_delete_scan_parser_minimal():
    argv = [
        "workbench-agent",
        "delete-scan",
        "--api-url",
        "https://test.com/api.php",
        "--api-user",
        "testuser",
        "--api-token",
        "testtoken",
        "--project-name",
        "MyProject",
        "--scan-name",
        "MyScan",
    ]
    with patch("sys.argv", argv):
        args = parse_cmdline_args()

    assert args.command == "delete-scan"
    assert args.project_name == "MyProject"
    assert args.scan_name == "MyScan"
    assert args.delete_identifications is False
    assert hasattr(args, "scan_number_of_tries")
    assert hasattr(args, "scan_wait_time")


def test_delete_scan_parser_with_delete_identifications():
    argv = [
        "workbench-agent",
        "delete-scan",
        "--api-url",
        "https://test.com/api.php",
        "--api-user",
        "testuser",
        "--api-token",
        "testtoken",
        "--project-name",
        "P",
        "--scan-name",
        "S",
        "--delete-identifications",
    ]
    with patch("sys.argv", argv):
        args = parse_cmdline_args()

    assert args.delete_identifications is True
