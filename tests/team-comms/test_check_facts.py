"""check_facts.py lists the numbers, links and code an edit dropped, and nothing else."""

from __future__ import annotations

import pytest

BEFORE = """# Upload outage

We have identified an issue that may have impacted users. Between 14:02 and 14:31 UTC,
12% of requests failed after the deploy of v2.4.1. See https://status.example.com/incidents.
Set `DB_PASSWORD` and read the [runbook](docs/runbook.md).

1. Roll back.
2. Watch the error rate.

```sh
helm rollback upload 41
```
"""


@pytest.fixture
def check(load_script):
    return load_script("check_facts")


def test_a_reworded_edit_that_keeps_every_fact_passes(check) -> None:
    after = """# Upload outage

Between 14:02 and 14:31 UTC, 12% of requests failed after the deploy of v2.4.1.
Details: https://status.example.com/incidents. Set `DB_PASSWORD`, then read the
[runbook](docs/runbook.md). Roll back, then watch the error rate.

```sh
helm rollback upload 41
```
"""
    assert check.dropped(BEFORE, after) == []


@pytest.mark.parametrize(
    ("cut", "kind", "value"),
    [
        ("12% of", "number", "12%"),
        ("14:31", "number", "14:31"),
        (
            " See https://status.example.com/incidents.",
            "link",
            "https://status.example.com/incidents",
        ),
        ("[runbook](docs/runbook.md)", "link", "docs/runbook.md"),
        ("`DB_PASSWORD`", "code", "DB_PASSWORD"),
    ],
)
def test_each_dropped_fact_is_named(check, cut: str, kind: str, value: str) -> None:
    assert (kind, value) in check.dropped(BEFORE, BEFORE.replace(cut, ""))


def test_a_changed_code_block_is_reported(check) -> None:
    after = BEFORE.replace("upload 41", "upload 40")
    assert ("code-block", "helm rollback upload 41") in check.dropped(BEFORE, after)


def test_renumbering_or_unlisting_steps_is_not_a_dropped_number(check) -> None:
    after = BEFORE.replace("1. Roll back.\n2. Watch the error rate.", "Roll back and watch.")
    assert [k for k, _ in check.dropped(BEFORE, after) if k == "number"] == []


def test_cutting_a_repeated_fact_is_not_reported(check) -> None:
    before = "The limit is 500 requests.\n\nRemember: the limit is 500 requests.\n"
    assert check.dropped(before, "The limit is 500 requests.\n") == []


def test_main_lists_what_was_dropped_and_exits_one(check, tmp_path, capsys) -> None:
    before, after = tmp_path / "before.md", tmp_path / "after.md"
    before.write_text(BEFORE, encoding="utf-8")
    after.write_text(BEFORE.replace("12% of", ""), encoding="utf-8")
    assert check.main([str(before), str(after)]) == 1
    assert "dropped number: 12%" in capsys.readouterr().out


def test_main_exits_zero_when_nothing_was_dropped(check, tmp_path) -> None:
    before = tmp_path / "before.md"
    before.write_text(BEFORE, encoding="utf-8")
    assert check.main([str(before), str(before)]) == 0


def test_a_missing_file_is_unusable_input(check, tmp_path, capsys) -> None:
    present = tmp_path / "after.md"
    present.write_text("x", encoding="utf-8")
    assert check.main([str(tmp_path / "missing.md"), str(present)]) == 2
    assert "no such file" in capsys.readouterr().err
