"""Tests for security_doc_check.py on small synthetic documents."""

from __future__ import annotations

import importlib.util
import sys
import textwrap
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "plugins/security/scripts/security_doc_check.py"
FIXTURES = Path(__file__).parent / "fixtures"
CATALOG = FIXTURES / "mini_catalog.json"


def _load():
    spec = importlib.util.spec_from_file_location("security_doc_check", SCRIPT)
    module = importlib.util.module_from_spec(spec)
    sys.modules["security_doc_check"] = module
    spec.loader.exec_module(module)
    return module


sdc = _load()

GOOD_THREAT_MODEL = textwrap.dedent(
    """\
    # Threat model: claims upload

    ## Assets
    - Claim documents

    ## Data flow diagram
    ```mermaid
    flowchart LR
      user[Claimant] -->|HTTPS| api
      subgraph cloud[Trust boundary: cloud project]
        api[API] --> db[(Claims DB)]
      end
    ```

    ## Trust boundaries
    - Internet to API.

    ## Abuse cases
    - A claimant uploads another claimant's file name.

    ## Threat register
    | ID | STRIDE | Element | Scenario | Risk | Mitigation | Controls |
    | --- | --- | --- | --- | --- | --- | --- |
    | T-1 | S | user to API | stolen session | High | MFA for claimants | IA-2 |
    | T-2 | T, I | API to DB | tampering in transit | Medium | TLS everywhere | SC-7(5), SC-13 |
    | T-3 | R | API | no audit trail | Low | Log every upload | AU-2 |

    ## Assumptions and out of scope
    - The browser is untrusted.
    """
)

GOOD_COMPLIANCE_MAP = textwrap.dedent(
    """\
    # Compliance evidence map

    This document lists evidence and gaps. It is not an assessment, and it does not state that
    the system is compliant or authorized.

    ## Applicability
    The product is offered to a federal agency; the agency decides the framework.

    ## Control evidence
    | Control | Title | Status | Evidence | Gap | Next step |
    | --- | --- | --- | --- | --- | --- |
    | AU-2 | Event Logging | Evidence found | `app/log.py:12` | none | none |
    | IA-2 | Authentication | Partial evidence | `auth/login.py:40` | no MFA | add MFA |
    | SC-13 | Cryptographic Protection | No evidence found | - | no FIPS mode | enable |
    | AC-2 | Account Management | Not assessable from repo | - | process | ask owner |

    ## Sources
    - https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final
    """
)


def run(tmp_path: Path, text: str, kind: str, *extra: str, catalog: Path | None = CATALOG) -> int:
    doc = tmp_path / "doc.md"
    doc.write_text(text)
    args = [str(doc), "--kind", kind, *extra]
    if catalog is not None:
        args += ["--catalog", str(catalog)]
    return sdc.main(args)


def test_a_good_threat_model_passes(tmp_path, capsys):
    assert run(tmp_path, GOOD_THREAT_MODEL, "threat-model") == 0
    assert "ok" in capsys.readouterr().out


def test_a_good_compliance_map_passes(tmp_path, capsys):
    assert run(tmp_path, GOOD_COMPLIANCE_MAP, "compliance-map") == 0


# --- control IDs ---------------------------------------------------------------


def test_an_invented_control_ID_is_reported_with_its_line(tmp_path, capsys):
    text = GOOD_THREAT_MODEL.replace("| AU-2 |", "| AU-99 |")
    assert run(tmp_path, text, "threat-model") == 1
    assert "control ID AU-99 is not in the NIST SP 800-53 Rev 5 catalog" in capsys.readouterr().out


def test_an_enhancement_that_does_not_exist_is_reported(tmp_path, capsys):
    assert run(tmp_path, "See SC-7(99) and SC-7(5).\n", "any") == 1
    out = capsys.readouterr().out
    assert "SC-7(99)" in out and "SC-7(5)" not in out


@pytest.mark.parametrize("token", ["HTTP-2", "UTF-8", "TLS-1", "AC-130", "CVE-2024-1234", "x-AC-2"])
def test_tokens_that_only_look_like_control_IDs_are_ignored(tmp_path, token):
    assert run(tmp_path, f"We use {token} here.\n", "any") == 0


def test_a_missing_catalog_stops_the_run_instead_of_skipping_the_check(tmp_path, capsys):
    assert run(tmp_path, "AU-2\n", "any", catalog=None) == 2
    assert "--catalog" in capsys.readouterr().err


def test_skipping_the_id_check_must_be_explicit_and_says_so(tmp_path, capsys):
    assert run(tmp_path, "AU-99\n", "any", "--skip-id-check", catalog=None) == 0
    assert "NOT verified" in capsys.readouterr().err


def test_an_unreadable_document_is_a_usage_error(tmp_path, capsys):
    assert sdc.main([str(tmp_path / "nope.md"), "--kind", "any", "--skip-id-check"]) == 2


# --- threat model ----------------------------------------------------------------


def test_missing_sections_and_diagram_are_listed(tmp_path, capsys):
    assert run(tmp_path, "# Notes\nnothing here\n", "threat-model") == 1
    out = capsys.readouterr().out
    for fragment in (
        "data flow diagram section",
        "trust boundaries section",
        "abuse cases",
        "no ```mermaid block",
        "no threat register table",
    ):
        assert fragment in out


def test_a_diagram_without_a_trust_boundary_subgraph_fails(tmp_path, capsys):
    text = GOOD_THREAT_MODEL.replace("subgraph", "%% subgraph").replace("%% subgraph", "box")
    assert run(tmp_path, text, "threat-model") == 1
    assert "no `subgraph`" in capsys.readouterr().out


def test_a_threat_without_a_control_or_mitigation_is_named(tmp_path, capsys):
    text = GOOD_THREAT_MODEL.replace("| Log every upload | AU-2 |", "| - | - |")
    assert run(tmp_path, text, "threat-model") == 1
    out = capsys.readouterr().out
    assert "T-3 has no mitigation" in out
    assert "T-3 maps to no 800-53 control" in out


def test_no_mapping_with_a_reason_is_accepted(tmp_path):
    text = GOOD_THREAT_MODEL.replace("| AU-2 |", "| no mapping: product-specific |")
    assert run(tmp_path, text, "threat-model") == 0


def test_a_register_that_is_not_ranked_is_rejected(tmp_path, capsys):
    text = GOOD_THREAT_MODEL.replace("| High |", "| Low |").replace("| Low | Log", "| High | Log")
    assert run(tmp_path, text, "threat-model") == 1
    assert "not ranked" in capsys.readouterr().out


def test_a_threat_with_no_stride_category_or_risk_is_named(tmp_path, capsys):
    text = GOOD_THREAT_MODEL.replace("| S |", "| ? |").replace("| High |", "| soon |")
    assert run(tmp_path, text, "threat-model") == 1
    out = capsys.readouterr().out
    assert "T-1 names no STRIDE category" in out and "T-1 has no risk rating" in out


# --- compliance map ---------------------------------------------------------------


def test_a_compliance_claim_is_rejected(tmp_path, capsys):
    text = GOOD_COMPLIANCE_MAP + "\nThe system is FedRAMP compliant.\n"
    assert run(tmp_path, text, "compliance-map") == 1
    assert "reads as a compliance claim" in capsys.readouterr().out


@pytest.mark.parametrize(
    "claim",
    [
        "The product is fully authorized.",
        "It meets all requirements.",
        "We are ATO-ready.",
        "Logging fully implements AU-2.",
    ],
)
def test_other_claim_phrasings_are_rejected(tmp_path, claim):
    assert run(tmp_path, GOOD_COMPLIANCE_MAP + f"\n{claim}\n", "compliance-map") == 1


def test_the_notice_itself_is_not_flagged_as_a_claim(tmp_path):
    assert run(tmp_path, GOOD_COMPLIANCE_MAP, "compliance-map") == 0


def test_a_status_outside_the_four_words_is_rejected(tmp_path, capsys):
    text = GOOD_COMPLIANCE_MAP.replace("Evidence found", "Compliant")
    assert run(tmp_path, text, "compliance-map") == 1
    assert "status 'Compliant' is not one of" in capsys.readouterr().out


def test_evidence_status_with_an_empty_evidence_cell_is_rejected(tmp_path, capsys):
    text = GOOD_COMPLIANCE_MAP.replace("`app/log.py:12`", "none")
    assert run(tmp_path, text, "compliance-map") == 1
    assert "Evidence cell is empty" in capsys.readouterr().out


def test_missing_notice_sources_and_applicability_are_listed(tmp_path, capsys):
    text = (
        "| Control | Status | Evidence |\n| --- | --- | --- |\n| AU-2 | No evidence found | - |\n"
    )
    assert run(tmp_path, text, "compliance-map") == 1
    out = capsys.readouterr().out
    assert "evidence and gaps" in out and "not an assessment" in out
    assert "applicability section" in out and "sources section" in out and "no source URL" in out


def test_a_map_with_no_control_table_is_rejected(tmp_path, capsys):
    text = "\n".join(line for line in GOOD_COMPLIANCE_MAP.splitlines() if not line.startswith("|"))
    assert run(tmp_path, text, "compliance-map") == 1
    assert "no control table" in capsys.readouterr().out


def test_escaped_pipes_do_not_shift_the_columns(tmp_path):
    text = GOOD_COMPLIANCE_MAP.replace("Event Logging", "Event \\| Logging")
    assert run(tmp_path, text, "compliance-map") == 0


# --- the plugin's own files -----------------------------------------------------


def test_every_control_ID_written_inside_the_plugin_exists_in_the_nist_catalog():
    known = {
        sdc.to_catalog_id(line)
        for line in (FIXTURES / "sp800-53r5-ids.txt").read_text().splitlines()
        if line and not line.startswith("#")
    }
    bad = []
    plugin = ROOT / "plugins/security"
    for path in sorted(plugin.rglob("*.md")):
        for number, line in enumerate(path.read_text().splitlines(), start=1):
            for match in sdc.CONTROL_ID.finditer(line):
                if sdc.to_catalog_id(match.group(0)) not in known:
                    bad.append(f"{path.relative_to(ROOT)}:{number}: {match.group(0)}")
    assert not bad, "invented or retired control IDs: " + "; ".join(bad)
