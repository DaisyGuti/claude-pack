"""Tests for scripts/validate.py: which validator output counts as a failure."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

SPEC = importlib.util.spec_from_file_location(
    "validate", Path(__file__).resolve().parents[2] / "scripts" / "validate.py"
)
assert SPEC and SPEC.loader
validate = importlib.util.module_from_spec(SPEC)
sys.modules["validate"] = validate
SPEC.loader.exec_module(validate)

VERSION_WARNING = {"path": "version", "message": "No version specified. Consider adding one"}


def test_missing_version_warning_is_allowed() -> None:
    report = {"success": True, "manifest": {"errors": [], "warnings": [VERSION_WARNING]}}
    assert validate.blocking_problems(report) == []


def test_other_warning_blocks() -> None:
    other = {"path": "skills", "message": "Default skills/ folder is ignored"}
    report = {"success": True, "manifest": {"errors": [], "warnings": [VERSION_WARNING, other]}}
    assert validate.blocking_problems(report) == [
        "warning: skills: Default skills/ folder is ignored"
    ]


def test_error_blocks_even_inside_contents() -> None:
    report = {
        "success": False,
        "manifest": {"errors": [], "warnings": []},
        "contents": [{"errors": [{"path": "SKILL.md", "message": "bad frontmatter"}]}],
    }
    assert validate.blocking_problems(report) == ["error: SKILL.md: bad frontmatter"]


def test_failure_without_listed_error_still_blocks() -> None:
    assert validate.blocking_problems({"success": False}) == [
        "validator reported failure without a listed error"
    ]
