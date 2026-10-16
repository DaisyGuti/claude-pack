"""Tests for nist_catalog.py. A tiny synthetic catalog stands in for NIST's 10 MB file."""

from __future__ import annotations

import importlib.util
import json
import shutil
import sys
import urllib.error
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "plugins/security/scripts/nist_catalog.py"
FIXTURES = Path(__file__).parent / "fixtures"


def _load():
    spec = importlib.util.spec_from_file_location("nist_catalog", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["nist_catalog"] = module
    spec.loader.exec_module(module)
    return module


nc = _load()


@pytest.fixture
def nist_dir(tmp_path):
    shutil.copy(FIXTURES / "mini_catalog.json", tmp_path / nc.CATALOG_FILE)
    shutil.copy(FIXTURES / "mini_moderate.json", tmp_path / nc.BASELINE_FILES["moderate"])
    return tmp_path


@pytest.mark.parametrize(
    ("display", "catalog"),
    [("AC-2", "ac-2"), ("SC-7(5)", "sc-7.5"), (" au-12 ", "au-12"), ("sc-7(20)", "sc-7.20")],
)
def test_ids_convert_both_ways(display, catalog):
    assert nc.to_catalog_id(display) == catalog
    assert nc.to_display_id(catalog) == display.strip().upper()


def test_load_catalog_includes_enhancements(nist_dir):
    titles = nc.load_catalog(nist_dir)
    assert titles["sc-7"] == "Boundary Protection"
    assert titles["sc-7.5"].startswith("Deny by Default")
    assert "ac-9" not in titles


def test_missing_catalog_says_how_to_fetch(tmp_path, capsys):
    assert nc.main(["show", "--dir", str(tmp_path), "AC-2"]) == 2
    assert "fetch" in capsys.readouterr().err


def test_corrupt_catalog_is_reported_not_crashed(tmp_path, capsys):
    (tmp_path / nc.CATALOG_FILE).write_text("<html>rate limited</html>")
    assert nc.main(["ids", "--dir", str(tmp_path)]) == 2
    assert "not valid JSON" in capsys.readouterr().err


def test_show_prints_titles_and_exits_one_for_an_unknown_id(nist_dir, capsys):
    assert nc.main(["show", "--dir", str(nist_dir), "AC-2", "SC-7(5)"]) == 0
    out = capsys.readouterr().out
    assert "AC-2\tAccount Management" in out
    assert "SC-7(5)\tDeny by Default" in out
    assert nc.main(["show", "--dir", str(nist_dir), "AC-99"]) == 1
    assert "AC-99\tNOT FOUND" in capsys.readouterr().out


def test_baseline_lists_titles_and_can_drop_enhancements(nist_dir, capsys):
    assert nc.main(["baseline", "--dir", str(nist_dir), "moderate"]) == 0
    lines = capsys.readouterr().out.splitlines()
    assert lines[0] == "AC-2\tAccount Management"
    assert "AC-2(1)\tAutomated System Account Management" in lines
    assert nc.main(["baseline", "--dir", str(nist_dir), "moderate", "--no-enhancements"]) == 0
    assert all("(" not in line for line in capsys.readouterr().out.splitlines())


def test_baseline_that_was_not_fetched_names_the_file(nist_dir, capsys):
    assert nc.main(["baseline", "--dir", str(nist_dir), "high"]) == 2
    assert "HIGH-baseline" in capsys.readouterr().err


def test_ids_lists_every_control(nist_dir, capsys):
    assert nc.main(["ids", "--dir", str(nist_dir)]) == 0
    assert capsys.readouterr().out.split() == [
        "AC-2",
        "AC-2(1)",
        "AU-2",
        "AU-12",
        "IA-2",
        "SC-7",
        "SC-7(5)",
        "SC-13",
        "SI-10",
    ]


class _Response:
    def __init__(self, body: bytes):
        self._body = body

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def read(self):
        return self._body


def test_fetch_saves_the_catalog_and_three_baselines(tmp_path, monkeypatch, capsys):
    body = (FIXTURES / "mini_catalog.json").read_bytes()
    seen = []

    def fake_urlopen(url, timeout):
        seen.append(url)
        return _Response(body)

    monkeypatch.setattr(nc.urllib.request, "urlopen", fake_urlopen)
    assert nc.main(["fetch", "--dest", str(tmp_path / "cache")]) == 0
    assert len(seen) == 4 and all(u.startswith(nc.BASE_URL) for u in seen)
    assert (tmp_path / "cache" / nc.CATALOG_FILE).exists()
    assert "Mini catalog for tests" in capsys.readouterr().out


def test_fetch_failure_exits_two_and_says_what_to_check(tmp_path, monkeypatch, capsys):
    def boom(url, timeout):
        raise urllib.error.URLError("offline")

    monkeypatch.setattr(nc.urllib.request, "urlopen", boom)
    assert nc.main(["fetch", "--dest", str(tmp_path)]) == 2
    assert "could not download" in capsys.readouterr().err


def test_fetch_refuses_a_response_that_is_not_json(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr(
        nc.urllib.request, "urlopen", lambda url, timeout: _Response(b"<html>error</html>")
    )
    assert nc.main(["fetch", "--dest", str(tmp_path)]) == 2
    assert not (tmp_path / nc.CATALOG_FILE).exists()


def test_the_reference_id_list_matches_the_shape_the_checker_expects():
    ids = [
        line
        for line in (FIXTURES / "sp800-53r5-ids.txt").read_text().splitlines()
        if not line.startswith("#")
    ]
    assert "AU-2" in ids and "SC-7(5)" in ids and "SC-13" in ids
    assert all(json.dumps(i) and nc.to_display_id(nc.to_catalog_id(i)) == i for i in ids)
