#!/usr/bin/env python3
"""Turn a ticket's labels into the Claude model that should work it.

A ticket carries one model label (`model:sonnet`, `model:workhorse`, ...). The registry's
"Model labels" table maps each label to a tier; this script maps the tier to a Claude model
alias and reads an optional `effort:<level>` label. Aliases (`haiku`, `sonnet`, `opus`) always
resolve to the newest model of that family, so this file never carries a model version.

Usage:
    resolve_model.py [--registry FILE] LABEL [LABEL ...]   labels as read from the ticket
    resolve_model.py --tier fast|workhorse|frontier         tier to model, for reports

Prints one JSON object: {"tier", "model", "effort", "label"}. `effort` is null unless the
ticket carries an `effort:<level>` label; the worker agent's own default applies then.

Exit codes: 0 resolved, 2 bad input, 3 no model label, 4 conflicting model labels,
5 a model label that maps to no tier.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

if sys.version_info < (3, 11):  # noqa: UP036  (a clear message on an older python3)
    sys.exit("resolve_model.py needs Python 3.11 or newer; install it and run this again")

sys.path.insert(0, str(Path(__file__).resolve().parent))
import registry  # noqa: E402  (sibling script; path set just above)

TIER_MODEL = {"fast": "haiku", "workhorse": "sonnet", "frontier": "opus"}
FAMILY_TIER = {"haiku": "fast", "sonnet": "workhorse", "opus": "frontier"}
EFFORT_LEVELS = ("low", "medium", "high", "xhigh", "max")

EXIT_BAD_INPUT = 2
EXIT_NO_LABEL = 3
EXIT_CONFLICT = 4
EXIT_UNRECOGNIZED = 5


def tier_of(label: str, table: dict[str, str]) -> str | None:
    """Map one `model:*` label to a tier, or None when it maps to nothing."""
    if label in table:
        return table[label]
    value = label.removeprefix("model:")
    if value in TIER_MODEL:
        return value
    if value in FAMILY_TIER:
        return FAMILY_TIER[value]
    match = re.fullmatch(r"claude-(haiku|sonnet|opus)(?:-.+)?", value)
    if match:
        return FAMILY_TIER[match.group(1)]
    return None


def resolve(labels: list[str], table: dict[str, str]) -> tuple[int, dict[str, object]]:
    """Resolve ticket labels to a model. `table` maps registry model labels to tiers."""
    model_labels = [label for label in labels if label.startswith("model:") or label in table]
    if not model_labels:
        return EXIT_NO_LABEL, {"error": "no model label on the ticket"}
    tiers: dict[str, str] = {}
    for label in model_labels:
        tier = tier_of(label, table)
        if tier is None:
            return EXIT_UNRECOGNIZED, {"error": f"unrecognized model label: {label}"}
        tiers[label] = tier
    if len(set(tiers.values())) > 1:
        return EXIT_CONFLICT, {"error": f"conflicting model labels: {', '.join(model_labels)}"}
    tier = next(iter(tiers.values()))
    effort = None
    for label in labels:
        value = label.removeprefix("effort:") if label.startswith("effort:") else None
        if value in EFFORT_LEVELS:
            effort = value
    return 0, {"tier": tier, "model": TIER_MODEL[tier], "effort": effort, "label": model_labels[0]}


def registry_table(path: Path | None) -> dict[str, str]:
    """Read {label: tier} from the registry's Model labels table; empty without a registry."""
    if path is None:
        return {}
    reg = registry.parse(path.read_text(encoding="utf-8"))
    return {row["label"]: tier for tier, row in reg["model_labels"].items() if row["label"]}


def main(argv: list[str]) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("labels", nargs="*", help="labels on the ticket")
    parser.add_argument("--registry", type=Path, help="registry.md, for its Model labels table")
    parser.add_argument("--tier", choices=sorted(TIER_MODEL), help="print the model for a tier")
    args = parser.parse_args(argv)

    if args.tier:
        print(json.dumps({"tier": args.tier, "model": TIER_MODEL[args.tier], "effort": None}))
        return 0
    if not args.labels:
        print("error: pass the ticket's labels, or --tier", file=sys.stderr)
        return EXIT_BAD_INPUT
    if args.registry and not args.registry.is_file():
        print(
            f"error: no registry file at {args.registry}; run registry.py ensure first",
            file=sys.stderr,
        )
        return EXIT_BAD_INPUT
    code, payload = resolve(args.labels, registry_table(args.registry))
    print(json.dumps(payload))
    return code


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
