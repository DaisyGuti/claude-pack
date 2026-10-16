#!/usr/bin/env python3
"""Summarize Claude Code token use and list-price cost from the local session transcripts.

Reads every session and subagent transcript under the Claude Code projects directory,
groups the assistant responses by model, subagent type, project and session, prices them
from a dated table (prices.json next to this script), and lists subagent runs that used a
top-tier model for work that looks mechanical.

Usage:
    python3 usage_report.py [--since 7d|24h|all|YYYY-MM-DD] [--dir PROJECTS_DIR]
                            [--prices FILE] [--top N] [--json]

The transcript layout is documented at https://code.claude.com/docs/en/claude-directory
(projects/<project>/<session>.jsonl and projects/<project>/<session>/subagents/). The fields
inside each line are not documented, so this script reads only the ones it needs and skips
anything it cannot parse. See references/transcript-format.md next to SKILL.md.

The dollar figures are list-price estimates. On a subscription plan they are not a bill.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
DEFAULT_PRICES = SCRIPT_DIR / "prices.json"

# Prices changed between model releases within weeks of each other in the table this
# script ships with, so a table older than this is worth a fresh look before trusting totals.
STALE_PRICE_DAYS = 45

# A subagent run that wrote at most this many output tokens in total (thinking included)
# returned a short answer. Together with "edited nothing and spawned nothing" it marks a
# run that read and reported, which is the mechanical shape. Override with --mech-output-max.
MECH_OUTPUT_MAX = 8000

TOP_TIERS = {"top", "frontier"}
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}
SPAWN_TOOLS = {"Agent", "Task"}
MECHANICAL_WORDS = re.compile(
    r"search|find|list|inventor|scan|grep|collect|extract|count|summar|lookup|locate|gather|rename",
    re.I,
)
JUDGMENT_WORDS = re.compile(
    r"review|audit|design|architect|security|judg|verif|decid|plan|debug|root.?cause|threat",
    re.I,
)
LABEL_WIDTH = 60
READ_ONLY_TOOLS = {
    "Read",
    "Grep",
    "Glob",
    "LSP",
    "WebFetch",
    "WebSearch",
    "TodoWrite",
    "TaskCreate",
}
SKIPPED_MODELS = {"<synthetic>", ""}


class UsageError(Exception):
    """A problem the user can fix; main() prints it and exits 2."""


# ---------------------------------------------------------------------------
# Prices
# ---------------------------------------------------------------------------


def load_prices(path: Path) -> dict[str, Any]:
    try:
        table = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise UsageError(
            f"price table not found: {path}. Pass --prices FILE or restore it."
        ) from None
    except json.JSONDecodeError as exc:
        raise UsageError(
            f"price table {path} is not valid JSON ({exc}). Fix or replace it."
        ) from None
    if not isinstance(table.get("models"), list) or "as_of" not in table:
        raise UsageError(f"price table {path} needs 'as_of' and a 'models' list.")
    return table


def normalize_model(model: str) -> str:
    """Reduce a cloud-partner id (us.anthropic.claude-...-v1:0) to the part from 'claude-'."""
    idx = model.find("claude-")
    return model[idx:] if idx >= 0 else model


def find_price(model: str, table: dict[str, Any]) -> dict[str, Any] | None:
    name = normalize_model(model)
    best: dict[str, Any] | None = None
    for entry in table["models"]:
        match = entry["match"]
        if name.startswith(match) and (best is None or len(match) > len(best["match"])):
            best = entry
    return best


def request_cost(usage: dict[str, int], price: dict[str, Any]) -> float:
    rates = price
    threshold = price.get("long_prompt_tokens")
    if threshold and "long" in price:
        prompt = (
            usage["input"] + usage["cache_read"] + usage["cache_write_5m"] + usage["cache_write_1h"]
        )
        if prompt > threshold:
            rates = price["long"]
    total = (
        usage["input"] * rates["input"]
        + usage["cache_write_5m"] * rates["cache_write_5m"]
        + usage["cache_write_1h"] * rates["cache_write_1h"]
        + usage["cache_read"] * rates["cache_read"]
        + usage["output"] * rates["output"]
    )
    return total / 1_000_000


# ---------------------------------------------------------------------------
# Reading transcripts
# ---------------------------------------------------------------------------


@dataclass
class Source:
    """Where a transcript file sits: main session or subagent, and which project."""

    kind: str  # "main" or "subagent"
    project: str
    session: str
    agent_id: str = ""
    agent_type: str = "main"
    description: str = ""
    requested_model: str = ""


@dataclass
class Call:
    """One API response. Claude Code writes one line per content block, so lines merge."""

    message_id: str
    model: str
    timestamp: datetime | None
    usage: dict[str, int]
    tools: dict[str, str]  # tool_use id -> tool name
    source: Source


def find_transcripts(root: Path) -> list[Path]:
    files = [p for p in root.rglob("*.jsonl") if ".orphaned-" not in p.name]
    return sorted(files)


def classify(path: Path, root: Path) -> Source:
    rel = path.relative_to(root).parts
    if len(rel) >= 4 and rel[-2] == "subagents":
        source = Source(kind="subagent", project=rel[0], session=rel[-3], agent_id=path.stem)
        meta_path = path.with_suffix(".meta.json")
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            meta = {}
        if isinstance(meta, dict):
            source.agent_type = str(meta.get("agentType") or "unknown")
            source.description = str(meta.get("description") or "")
            source.requested_model = str(meta.get("model") or "")
        else:
            source.agent_type = "unknown"
        return source
    return Source(kind="main", project=rel[0], session=path.stem)


def parse_time(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def read_usage(raw: dict[str, Any]) -> dict[str, int]:
    def num(value: Any) -> int:
        return value if isinstance(value, int) and not isinstance(value, bool) else 0

    created = num(raw.get("cache_creation_input_tokens"))
    split = raw.get("cache_creation")
    five = one = 0
    if isinstance(split, dict):
        five = num(split.get("ephemeral_5m_input_tokens"))
        one = num(split.get("ephemeral_1h_input_tokens"))
    if five + one == 0:
        five = created  # no breakdown recorded: price at the 5 minute write rate
    details = raw.get("output_tokens_details")
    thinking = num(details.get("thinking_tokens")) if isinstance(details, dict) else 0
    return {
        "input": num(raw.get("input_tokens")),
        "output": num(raw.get("output_tokens")),
        "cache_read": num(raw.get("cache_read_input_tokens")),
        "cache_write_5m": five,
        "cache_write_1h": one,
        "thinking": thinking,
    }


@dataclass
class LoadStats:
    files: int = 0
    skipped_lines: int = 0
    undated: int = 0
    calls_seen: int = 0


def load_calls(root: Path, since: datetime | None) -> tuple[list[Call], LoadStats]:
    stats = LoadStats()
    by_id: dict[str, Call] = {}
    for path in find_transcripts(root):
        stats.files += 1
        source = classify(path, root)
        try:
            handle = path.open(encoding="utf-8")
        except OSError:
            stats.skipped_lines += 1
            continue
        with handle:
            for line in handle:
                line = line.strip()
                if not line:
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    stats.skipped_lines += 1
                    continue
                absorb(entry, source, by_id)
    calls = []
    for call in by_id.values():
        stats.calls_seen += 1
        if since is not None:
            if call.timestamp is None:
                stats.undated += 1
                continue
            if call.timestamp < since:
                continue
        calls.append(call)
    return calls, stats


def absorb(entry: Any, source: Source, by_id: dict[str, Call]) -> None:
    if not isinstance(entry, dict) or entry.get("type") != "assistant":
        return
    message = entry.get("message")
    if not isinstance(message, dict) or not isinstance(message.get("usage"), dict):
        return
    model = str(message.get("model") or "")
    if model in SKIPPED_MODELS:
        return
    message_id = str(message.get("id") or entry.get("requestId") or entry.get("uuid") or "")
    if not message_id:
        return
    usage = read_usage(message["usage"])
    tools: dict[str, str] = {}
    content = message.get("content")
    if isinstance(content, list):
        for block in content:
            if isinstance(block, dict) and block.get("type") == "tool_use":
                tools[str(block.get("id") or len(tools))] = str(block.get("name") or "?")
    stamp = parse_time(entry.get("timestamp"))
    existing = by_id.get(message_id)
    if existing is None:
        by_id[message_id] = Call(message_id, model, stamp, usage, tools, source)
        return
    existing.tools.update(tools)
    if stamp and (existing.timestamp is None or stamp < existing.timestamp):
        existing.timestamp = stamp
    if usage["output"] > existing.usage["output"]:
        existing.usage = usage  # only the last streamed line carries the final output count


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------


@dataclass
class Agg:
    calls: int = 0
    input: int = 0
    output: int = 0
    cache_read: int = 0
    cache_write: int = 0
    cost: float = 0.0

    def add(self, usage: dict[str, int], cost: float) -> None:
        self.calls += 1
        self.input += usage["input"]
        self.output += usage["output"]
        self.cache_read += usage["cache_read"]
        self.cache_write += usage["cache_write_5m"] + usage["cache_write_1h"]
        self.cost += cost

    def row(self) -> dict[str, Any]:
        return {
            "calls": self.calls,
            "input": self.input,
            "output": self.output,
            "cache_read": self.cache_read,
            "cache_write": self.cache_write,
            "cost_usd": round(self.cost, 4),
        }


@dataclass
class Run:
    """All the responses of one subagent transcript."""

    source: Source
    agg: Agg = field(default_factory=Agg)
    models: defaultdict[str, float] = field(
        default_factory=lambda: defaultdict(float)
    )  # model -> USD
    model_calls: Counter[str] = field(default_factory=Counter)
    tools: Counter[str] = field(default_factory=Counter)
    usages: list[dict[str, int]] = field(default_factory=list)


def build_report(
    calls: list[Call], stats: LoadStats, table: dict[str, Any], top: int, mech_output_max: int
) -> dict[str, Any]:
    total = Agg()
    by_model: dict[str, Agg] = {}
    by_agent: dict[str, Agg] = {}
    by_project: dict[str, Agg] = {}
    by_session: dict[str, Agg] = {}
    runs: dict[tuple[str, str], Run] = {}
    unpriced: Counter[str] = Counter()

    for call in calls:
        price = find_price(call.model, table)
        if price is None:
            unpriced[call.model] += 1
            cost = 0.0
        else:
            cost = request_cost(call.usage, price)
        src = call.source
        total.add(call.usage, cost)
        for bucket, key in (
            (by_model, call.model),
            (by_agent, src.agent_type),
            (by_project, src.project),
            (by_session, f"{src.project}/{src.session}"),
        ):
            bucket.setdefault(key, Agg()).add(call.usage, cost)
        if src.kind == "subagent":
            run = runs.setdefault((src.session, src.agent_id), Run(src))
            run.agg.add(call.usage, cost)
            run.models[call.model] += cost
            run.model_calls[call.model] += 1
            run.tools.update(call.tools.values())
            run.usages.append(call.usage)

    warnings = []
    age = (datetime.now(UTC).date() - datetime.fromisoformat(table["as_of"]).date()).days
    if age > STALE_PRICE_DAYS:
        warnings.append(
            f"price table is {age} days old (as of {table['as_of']}); refresh it from "
            f"{table.get('source', 'the pricing page')} and pass --prices before trusting dollars"
        )
    if unpriced:
        warnings.append(
            "no price for: "
            + ", ".join(sorted(unpriced))
            + "; their cost counts as $0 in every total"
        )
    if stats.skipped_lines:
        warnings.append(f"{stats.skipped_lines} unreadable transcript lines were skipped")
    if stats.undated:
        warnings.append(
            f"{stats.undated} responses had no timestamp and were left out of this window"
        )

    model_rows = []
    for name, agg in sorted(by_model.items(), key=lambda kv: -kv[1].cost):
        price = find_price(name, table)
        model_rows.append(
            {"model": name, "tier": price["tier"] if price else "unpriced", **agg.row()}
        )

    return {
        "price_table": {"as_of": table["as_of"], "source": table.get("source", "")},
        "files": stats.files,
        "warnings": warnings,
        "totals": total.row(),
        "by_model": model_rows,
        "by_agent": ranked(by_agent, "agent_type", top),
        "by_project": ranked(by_project, "project", top),
        "by_session": ranked(by_session, "session", top),
        "top_tier_candidates": find_candidates(list(runs.values()), table, mech_output_max)[:top],
    }


def ranked(buckets: dict[str, Agg], label: str, top: int) -> list[dict[str, Any]]:
    ordered = sorted(buckets.items(), key=lambda kv: -kv[1].cost)[:top]
    return [{label: key, **agg.row()} for key, agg in ordered]


def find_candidates(
    runs: list[Run], table: dict[str, Any], mech_output_max: int
) -> list[dict[str, Any]]:
    """Subagent runs on a top-tier model whose shape looks mechanical. A lead, not a verdict."""
    refs = table.get("reference_models", {})
    found = []
    for run in runs:
        model = max(run.models, key=lambda m: run.models[m])
        price = find_price(model, table)
        if price is None or price["tier"] not in TOP_TIERS:
            continue
        used = set(run.tools)
        if used & EDIT_TOOLS or used & SPAWN_TOOLS or run.agg.output > mech_output_max:
            continue
        label = f"{run.source.agent_type} {run.source.description}"
        reasons = [
            f"top-tier model {model}",
            f"edited and spawned nothing; {run.agg.output} output tokens in {run.agg.calls} calls",
        ]
        if "Bash" in used:
            reasons.append(
                "ran Bash, which can change files; check the commands before downshifting"
            )
        if MECHANICAL_WORDS.search(label):
            reasons.append("name or description reads as search, list or summarize work")
        row: dict[str, Any] = {
            "agent_type": run.source.agent_type,
            "description": run.source.description,
            "session": f"{run.source.project}/{run.source.session}",
            "model": model,
            "requested_model": run.source.requested_model,
            "calls": run.agg.calls,
            "output_tokens": run.agg.output,
            "tools": dict(run.tools),
            "read_only": used <= READ_ONLY_TOOLS,
            "ran_bash": "Bash" in used,
            "cost_usd": round(run.agg.cost, 4),
            "judgment_hint": bool(JUDGMENT_WORDS.search(label)),
            "reasons": reasons,
        }
        for label_name, ref_model in refs.items():
            ref_price = find_price(ref_model, table)
            if ref_price is not None:
                est = sum(request_cost(u, ref_price) for u in run.usages)
                row[f"cost_usd_at_{label_name}"] = round(est, 4)
        found.append(row)
    return sorted(found, key=lambda r: -r["cost_usd"])


# ---------------------------------------------------------------------------
# Output
# ---------------------------------------------------------------------------


def fmt_tokens(n: int) -> str:
    if n >= 1_000_000:
        return f"{n / 1_000_000:.1f}M"
    if n >= 1_000:
        return f"{n / 1_000:.1f}k"
    return str(n)


def shorten(name: str, width: int) -> str:
    """Keep the end of a long label: project paths and session ids differ at the tail."""
    return name if len(name) <= width else "..." + name[-(width - 3) :]


def table_text(title: str, label: str, rows: list[dict[str, Any]], extra: str = "") -> list[str]:
    if not rows:
        return []
    width = min(LABEL_WIDTH, max(len(str(r[label])) for r in rows))
    out = [
        "",
        title,
        f"  {label:<{width}}  {extra:<8} {'calls':>6} {'in':>8} {'out':>8} "
        f"{'cache rd':>9} {'cache wr':>9} {'cost':>9}",
    ]
    for r in rows:
        name = shorten(str(r[label]), width)
        out.append(
            f"  {name:<{width}}  {str(r.get(extra.strip(), '')):<8} {r['calls']:>6} "
            f"{fmt_tokens(r['input']):>8} {fmt_tokens(r['output']):>8} "
            f"{fmt_tokens(r['cache_read']):>9} {fmt_tokens(r['cache_write']):>9} "
            f"{'$' + format(r['cost_usd'], ',.2f'):>9}"
        )
    return out


def render_text(report: dict[str, Any], window: str) -> str:
    t = report["totals"]
    lines = [
        f"Claude Code usage, window: {window}",
        f"Transcript files read: {report['files']}. "
        f"Price table as of {report['price_table']['as_of']} ({report['price_table']['source']}).",
        "Dollar figures are list-price estimates; on a subscription plan they are not a bill.",
        f"Total: {t['calls']} responses, {fmt_tokens(t['input'])} fresh input, "
        f"{fmt_tokens(t['output'])} output, {fmt_tokens(t['cache_read'])} cache reads, "
        f"{fmt_tokens(t['cache_write'])} cache writes, ${t['cost_usd']:,.2f}",
    ]
    for w in report["warnings"]:
        lines.append(f"WARNING: {w}")
    lines += table_text("By model", "model", report["by_model"], "tier")
    lines += table_text(
        "By subagent type (main = the main conversation)", "agent_type", report["by_agent"]
    )
    lines += table_text("By project", "project", report["by_project"])
    lines += table_text("By session (most expensive)", "session", report["by_session"])
    cands = report["top_tier_candidates"]
    lines += ["", "Top-tier subagent runs that look mechanical (leads to confirm, not verdicts)"]
    if not cands:
        lines.append("  none")
    for c in cands:
        hint = ""
        if c["judgment_hint"]:
            hint += "  [description reads as judgment work; probably keep]"
        if c["ran_bash"]:
            hint += "  [ran Bash; confirm it only read]"
        lines.append(
            f"  {c['agent_type']}: {c['description'][:70]!r} on {c['model']} "
            f"(asked for {c['requested_model'] or 'inherit'}), {c['calls']} calls, "
            f"{c['output_tokens']} out, ${c['cost_usd']:.2f}{hint}"
        )
        at = ", ".join(
            f"${c[k]:.2f} at {k.removeprefix('cost_usd_at_')}"
            for k in c
            if k.startswith("cost_usd_at_")
        )
        lines.append(f"      tools: {c['tools']}; same tokens would cost about {at}")
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def parse_since(value: str) -> datetime | None:
    if value == "all":
        return None
    match = re.fullmatch(r"(\d+)([dh])", value)
    if match:
        amount = int(match.group(1))
        delta = timedelta(days=amount) if match.group(2) == "d" else timedelta(hours=amount)
        return datetime.now(UTC) - delta
    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        raise UsageError(
            f"--since {value!r} is not understood. Use 7d, 24h, all, or a date such as 2026-10-01."
        ) from None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def default_projects_dir() -> Path:
    config = os.environ.get("CLAUDE_CONFIG_DIR")
    base = Path(config).expanduser() if config else Path.home() / ".claude"
    return base / "projects"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument(
        "--since", default="7d", help="window: 7d, 24h, all, or a date (default 7d)"
    )
    parser.add_argument("--dir", type=Path, help="projects directory (default ~/.claude/projects)")
    parser.add_argument("--prices", type=Path, default=DEFAULT_PRICES, help="price table JSON")
    parser.add_argument("--top", type=int, default=10, help="rows per ranked table (default 10)")
    parser.add_argument("--mech-output-max", type=int, default=MECH_OUTPUT_MAX)
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    args = parser.parse_args(argv)
    try:
        root = (args.dir or default_projects_dir()).expanduser()
        if not root.is_dir():
            raise UsageError(
                f"transcript directory not found: {root}. Run Claude Code once, or pass --dir "
                "(set CLAUDE_CONFIG_DIR if your config lives elsewhere)."
            )
        since = parse_since(args.since)
        table = load_prices(args.prices)
        calls, stats = load_calls(root, since)
    except UsageError as exc:
        print(f"usage_report: {exc}", file=sys.stderr)
        return 2
    report = build_report(calls, stats, table, args.top, args.mech_output_max)
    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print(render_text(report, args.since))
    return 0


if __name__ == "__main__":
    sys.exit(main())
