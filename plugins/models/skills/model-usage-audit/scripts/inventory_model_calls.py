#!/usr/bin/env python3
"""Inventory every place a codebase calls an AI model, with file:line evidence.

The script finds facts. It does not judge them. For each hit it records the provider, the
model ids, the settings that appear near a call (max tokens, timeout, retries, streaming,
prompt caching), routing hints (region, endpoint), dependency pins, secrets that look
hard-coded, prompt or log lines that may carry sensitive data, and files that look like
evals. The skill reads the code behind every hit before turning a hit into a finding.

Usage:
    python3 inventory_model_calls.py [ROOT] [--json] [--json-out FILE] [--deprecations FILE]
                                     [--limit N]

--deprecations takes a JSON file the caller builds from the providers' current deprecation
pages: {"as_of": "...", "models": {"<model id>": {"status": "...", "retires": "...",
"replacement": "...", "source": "<url>"}}}. This script never fetches anything, because the
lifecycle of a model id is a fast-moving fact that has to come from the provider's page.

Secrets are never printed. A hit shows the kind of secret, the file and line, and the
first four characters.
"""

# ruff: noqa: E501
# The pattern tables below are one regular expression per line on purpose: splitting a
# regex across lines makes it harder to compare against the SDK it matches.
from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from collections import Counter
from pathlib import Path
from typing import Any

PRUNE_DIRS = {
    ".git", "node_modules", ".venv", "venv", "env", "__pycache__", "dist", "build", "target",
    ".next", ".tox", ".mypy_cache", ".ruff_cache", ".pytest_cache", "coverage", "site-packages",
    ".terraform", "vendor", ".gradle", ".idea",
}  # fmt: skip
SCAN_SUFFIXES = {
    ".py", ".ipynb", ".js", ".jsx", ".mjs", ".cjs", ".ts", ".tsx", ".go", ".java", ".kt", ".rb",
    ".php", ".cs", ".rs", ".sh", ".yaml", ".yml", ".json", ".toml", ".tf", ".cfg", ".ini",
}  # fmt: skip
LOCKFILES = {
    "package-lock.json", "yarn.lock", "pnpm-lock.yaml", "uv.lock", "poetry.lock", "go.sum",
    "Pipfile.lock", "composer.lock", "Gemfile.lock",
}  # fmt: skip
MANIFESTS = {"package.json", "pyproject.toml", "go.mod", "Gemfile", "pom.xml", "build.gradle"}

# A file bigger than this is almost always generated data, not code that calls a model.
MAX_FILE_BYTES = 1_000_000
# Longest call (in lines) searched for settings. A formatted call with keyword arguments
# rarely spans more than this.
WINDOW_LINES = 25
# Lines searched after a hit that has no parenthesis, such as a URL in a shell script.
NO_PAREN_LINES = 5
# Lines longer than this are minified or generated; only the start is searched, which also
# keeps the regular expressions fast on a bundled file.
MAX_LINE_CHARS = 2000
SNIPPET_CHARS = 140

# (provider, kind, regex). kind: import, client, call, wrapper, endpoint.
SITE_PATTERNS: list[tuple[str, str, re.Pattern[str]]] = [
    (p, k, re.compile(r, re.I if p == "litellm" else 0))
    for p, k, r in [
        ("anthropic", "import", r"import\s+anthropic\b|from\s+anthropic\b|@anthropic-ai/(?:sdk|vertex-sdk|bedrock-sdk|foundry-sdk)|com\.anthropic\.|github\.com/anthropics/anthropic-sdk-go"),
        ("anthropic", "client", r"\b(?:Async)?Anthropic(?:Vertex|Bedrock(?:Mantle)?|Foundry|AWS)?\s*\("),
        ("anthropic", "call", r"\.(?:beta\.)?messages\.(?:create|stream|parse|count_tokens)\s*\(|\.messages\.batches\.create"),
        ("anthropic", "wrapper", r"\bChatAnthropic(?:Vertex)?\b|langchain_anthropic|@langchain/anthropic|@ai-sdk/anthropic"),
        ("anthropic", "wrapper", r"claude_agent_sdk|@anthropic-ai/claude-agent-sdk|claude_code_sdk"),
        ("anthropic", "endpoint", r"api\.anthropic\.com|publishers/anthropic/models"),
        ("openai", "import", r"import\s+openai\b|from\s+openai\b|from\s+['\"]openai['\"]|require\(['\"]openai['\"]\)|github\.com/openai/openai-go|com\.openai\."),
        ("openai", "client", r"\b(?:Async|Azure)?OpenAI\s*\("),
        ("openai", "call", r"\.chat\.completions\.(?:create|parse|stream)\s*\(|\.responses\.(?:create|parse|stream)\s*\(|\.embeddings\.create\s*\("),
        ("openai", "wrapper", r"\bChat(?:Azure)?OpenAI\b|OpenAIEmbeddings|langchain_openai|@langchain/openai|@ai-sdk/openai"),
        ("openai", "endpoint", r"api\.openai\.com|\.openai\.azure\.com"),
        ("gemini", "import", r"google\.generativeai|from\s+google\s+import\s+genai|import\s+vertexai|from\s+vertexai|@google/genai|@google/generative-ai|@google-cloud/vertexai|google\.golang\.org/genai|cloud\.google\.com/go/vertexai"),
        ("gemini", "client", r"\bgenai\.Client\s*\(|\bGenerativeModel\s*\(|\bGoogleGenerativeAI\s*\(|\bGoogleGenAI\s*\(|vertexai\.init\s*\("),
        ("gemini", "call", r"\.generate_content(?:_async|_stream)?\s*\(|\.generateContent(?:Stream)?\s*\(|\.embed_content\s*\("),
        ("gemini", "wrapper", r"\bChatVertexAI\b|\bChatGoogleGenerativeAI\b|VertexAIEmbeddings|@ai-sdk/google"),
        ("gemini", "endpoint", r"generativelanguage\.googleapis\.com|aiplatform\.googleapis\.com|\.rep\.googleapis\.com"),
        ("bedrock", "client", r"client\(\s*[\"']bedrock-runtime[\"']|BedrockRuntimeClient|bedrock-runtime"),
        ("bedrock", "call", r"\.(?:invoke_model(?:_with_response_stream)?|converse(?:_stream)?)\s*\(|InvokeModelCommand|ConverseCommand|ConverseStreamCommand"),
        ("bedrock", "wrapper", r"\bChatBedrock(?:Converse)?\b|langchain_aws|@langchain/aws|BedrockEmbeddings"),
        ("litellm", "wrapper", r"import\s+litellm\b|from\s+litellm\b|\blitellm\.a?completion\s*\("),
        ("langchain", "wrapper", r"\binit_chat_model\s*\(|from\s+langchain\b|langchain_core|@langchain/core"),
        ("llamaindex", "wrapper", r"llama_index\.llms|from\s+llama_index|from\s+['\"]llamaindex['\"]"),
        ("vercel-ai-sdk", "wrapper", r"from\s+['\"]ai['\"]|\b(?:generateText|streamText|generateObject)\s*\("),
        ("local-model", "endpoint", r"localhost:11434|127\.0\.0\.1:11434|\bimport\s+ollama\b|\bvllm\b"),
    ]
]  # fmt: skip

# (provider, regex) for model ids. Anthropic ids must name a family so that package names
# such as claude-agent-sdk are not read as models.
MODEL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (p, re.compile(r))
    for p, r in [
        ("anthropic", r"(?<![\w.-])(?:(?:us|eu|apac|global|jp|au|us-gov)\.)?(?:anthropic\.)?claude-(?:opus|sonnet|haiku|fable|mythos|instant|[1-3](?![0-9]))[a-z0-9.@:_-]*"),
        ("openai", r"(?<![\w.-])(?:gpt-[0-9][a-z0-9.-]*|chatgpt-[a-z0-9.-]+|text-embedding-[a-z0-9-]+|gpt-image-[a-z0-9-]+|dall-e-[0-9])"),
        ("openai", r"(?<=[\"'])o[134](?:-mini|-pro|-preview|-deep-research)?(?=[\"'])"),
        ("gemini", r"(?<![\w.-])(?:gemini|gemma|imagen|veo)-[a-z0-9][a-z0-9.-]*"),
        ("bedrock-other", r"(?<![\w.-])(?:amazon\.(?:nova|titan)-[a-z0-9:.-]+|meta\.llama[a-z0-9:._-]+|mistral\.[a-z0-9:._-]+|cohere\.[a-z0-9:._-]+)"),
    ]
]  # fmt: skip

WINDOW_SETTINGS: dict[str, re.Pattern[str]] = {
    name: re.compile(rx, re.I)
    for name, rx in {
        "max_tokens": r"max[_-]?(?:output[_-]?|completion[_-]?)?tokens|maxOutputTokens",
        "timeout": r"\btimeout|request_timeout|AbortSignal\.timeout",
        "retries": r"max[_-]?retries|maxRetries|\bretry|backoff|tenacity",
        "streaming": r"\bstream(?:ing)?\s*[=:]\s*true|\.stream\s*\(|streamText|_stream\b|ConverseStream|WithResponseStream",
        "prompt_caching": r"cache_control|cachedContent|cached_content|promptCacheKey|cachePoint",
        "effort_or_thinking": r"\beffort\b|\bthinking\b|reasoning_effort|thinkingConfig|thinking_budget",
        "sampling": r"\btemperature\b|\btop_p\b|\btop_k\b",
        "structured_output": r"output_config|response_format|response_schema|responseSchema|json_schema|tool_choice",
    }.items()
}  # fmt: skip
EXPECTED_SETTINGS = ("max_tokens", "timeout", "retries", "streaming", "prompt_caching")

ROUTING = re.compile(
    r"\b(?:region|aws_region|location|inference_geo|base_url|baseURL|api_base|endpoint|project_id|projectId)\b\s*[=:]",
    re.I,
)
LOG_LINE = re.compile(
    r"\b(?:log(?:ger)?\.\w+|logging\.\w+|print|console\.\w+|println)\s*\(.*\b(?:prompt|messages|completion|response|transcript|payload|user_input)\b",
    re.I,
)
PII_WORDS = re.compile(
    r"(?<![A-Za-z])(?:ssn|social_security|date_of_birth|dob|passport|patient|diagnos[a-z]*|salary|"
    r"credit_card|cardholder|drivers?_?licen[cs]e|biometric|cui|fouo|itar|classified|clearance|"
    r"taxpayer)(?![A-Za-z])",
    re.I,
)
GENERIC_SECRET = "literal api_key assignment"
SECRET_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("Anthropic API key", re.compile(r"sk-ant-[A-Za-z0-9_-]{20,}")),
    ("OpenAI-style API key", re.compile(r"\bsk-(?!ant-)(?:proj-)?[A-Za-z0-9_-]{32,}")),
    ("Google API key", re.compile(r"AIza[0-9A-Za-z_-]{35}")),
    ("AWS access key id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("private key block", re.compile(r"-----BEGIN (?:RSA |EC )?PRIVATE KEY-----")),
    (
        GENERIC_SECRET,
        re.compile(r"""api[_-]?key["']?\s*[=:]\s*["']([^"'\s]{12,})["']""", re.I),
    ),
]
PLACEHOLDER = re.compile(r"your|example|xxx|<|\$\{|changeme|placeholder|dummy|test|fake", re.I)

DEP_NAMES = [
    "anthropic", "openai", "google-genai", "google-generativeai", "google-cloud-aiplatform",
    "vertexai", "boto3", "litellm", "claude-agent-sdk", "langchain[\\w-]*", "llama-index[\\w-]*",
    "@anthropic-ai/[\\w-]+", "@google/genai", "@google/generative-ai", "@google-cloud/vertexai",
    "@langchain/[\\w-]+", "@ai-sdk/[\\w-]+", "ollama",
]  # fmt: skip
EVAL_DEP_NAMES = [
    "promptfoo", "deepeval", "ragas", "langsmith", "braintrust", "inspect-ai", "inspect_ai",
    "trulens", "openai-evals", "giskard", "langfuse",
]  # fmt: skip
DEP_RE = re.compile(r"(?<![\w@/.-])(" + "|".join(DEP_NAMES) + r")(?![\w-])([^\n]{0,60})")
EVAL_DEP_RE = re.compile(r"(?<![\w@/.-])(" + "|".join(EVAL_DEP_NAMES) + r")(?![\w-])")
EVAL_PATH = re.compile(
    r"(?:^|/)(?:evals?|evaluations?|promptfoo)(?:/|\.)|(?:^|[/_-])(?:eval|evals)[_.-]|_eval\.|golden",
    re.I,
)
ENV_NAME = re.compile(r"(?:^|/)\.env(?:\.[\w.-]+)?$")
ENV_TEMPLATE = re.compile(r"example|sample|template|dist|defaults?$", re.I)


class UsageError(Exception):
    """A problem the caller can fix; main() prints it and exits 2."""


URL_CREDENTIALS = re.compile(r"(://)[^/\s:@]+:[^/\s@]+@")
URL_SECRET_PARAM = re.compile(
    r"([?&](?:key|token|api[_-]?key|access[_-]?token|sig|signature)=)[^&\s\"']+", re.I
)


def redact(text: str) -> str:
    """Hide key shapes, URL credentials and secret-looking query parameters in a snippet."""
    for kind, rx in SECRET_PATTERNS:
        text = rx.sub(f"[{kind} redacted]", text)
    text = URL_CREDENTIALS.sub(r"\1[redacted]@", text)
    return URL_SECRET_PARAM.sub(r"\1[redacted]", text)


def snippet(line: str) -> str:
    return redact(line.strip())[:SNIPPET_CHARS]


def model_form(model_id: str) -> str:
    lowered = model_id.lower()
    if lowered.endswith("-latest") or "-latest" in lowered:
        return "latest-alias"
    if "preview" in lowered or "-exp" in lowered:
        return "preview"
    if re.search(r"@\d{8}|-\d{8}\b|-\d{4}-\d{2}-\d{2}\b", lowered):
        return "dated"
    return "undated"


def normalize_for_lookup(model_id: str) -> list[str]:
    """Spellings under which a provider page might list this id."""
    base = model_id.lower()
    idx = base.find("claude-")
    stripped = base[idx:] if idx >= 0 else base
    stripped = re.sub(r"-v\d+:\d+$", "", stripped)
    variants = [base, stripped, stripped.replace("@", "-")]
    return list(dict.fromkeys(variants))


def load_deprecations(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        raise UsageError(f"--deprecations file not found: {path}") from None
    except json.JSONDecodeError as exc:
        raise UsageError(f"--deprecations file {path} is not valid JSON ({exc}).") from None
    models = data.get("models") if isinstance(data, dict) else None
    if not isinstance(models, dict):
        raise UsageError(f'--deprecations file {path} needs a top-level "models" object.')
    return {k.lower(): v for k, v in models.items()}


def iter_files(root: Path, skipped: Counter[str], eval_names: list[str]) -> list[Path]:
    """Source files to read. Files whose path looks like an eval land in eval_names, whatever
    their suffix, because eval data is usually .jsonl or .csv and never read as code."""
    found: list[Path] = []
    for dirpath, dirnames, filenames in os.walk(root):
        if dirpath != str(root) and ".git" in filenames:
            skipped["linked git worktree"] += 1  # a second checkout of the same code
            dirnames[:] = []
            continue
        dirnames[:] = sorted(d for d in dirnames if d not in PRUNE_DIRS)
        for name in sorted(filenames):
            path = Path(dirpath) / name
            rel = path.relative_to(root).as_posix()
            if EVAL_PATH.search(rel):
                eval_names.append(rel)
            if name in LOCKFILES:
                skipped["lockfile"] += 1
                continue
            if path.suffix.lower() not in SCAN_SUFFIXES and not (
                ENV_NAME.search(name) or name in MANIFESTS or name.startswith("requirements")
            ):
                continue
            try:
                if path.stat().st_size > MAX_FILE_BYTES:
                    skipped["larger than 1 MB"] += 1
                    continue
            except OSError:
                continue
            found.append(path)
    return found


def read_lines(path: Path, skipped: Counter[str]) -> list[str] | None:
    try:
        raw = path.read_bytes()
    except OSError:
        skipped["unreadable"] += 1
        return None
    if b"\0" in raw[:4096]:
        skipped["binary"] += 1
        return None
    text = raw.decode("utf-8", errors="replace")
    return [line[:MAX_LINE_CHARS] for line in text.splitlines()]


def call_block(lines: list[str], index: int, column: int) -> str:
    """Text of the call that starts on lines[index] at column: from its opening parenthesis to
    the matching close, capped at WINDOW_LINES. Without a parenthesis (an endpoint string, a
    wrapper import) the next few lines are used."""
    depth = 0
    opened = False
    out: list[str] = []
    for offset, line in enumerate(lines[index : index + WINDOW_LINES]):
        text = line[column:] if offset == 0 else line
        out.append(text)
        for char in text:
            if char == "(":
                depth += 1
                opened = True
            elif char == ")" and opened:
                depth -= 1
        if opened and depth <= 0:
            return "\n".join(out)
        if not opened and offset >= NO_PAREN_LINES:
            break
    return "\n".join(out)


def settings_in(block: str) -> list[str]:
    return [name for name, rx in WINDOW_SETTINGS.items() if rx.search(block)]


def tracked_env_files(root: Path) -> list[str]:
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files"], capture_output=True, text=True, check=False
        )
    except FileNotFoundError:
        return []
    if out.returncode != 0:
        return []
    return [
        f
        for f in out.stdout.splitlines()
        if ENV_NAME.search(f) and not ENV_TEMPLATE.search(Path(f).name)
    ]


def scan(root: Path, deprecations: dict[str, Any]) -> dict[str, Any]:
    skipped: Counter[str] = Counter()
    eval_files: list[str] = []
    files = iter_files(root, skipped, eval_files)
    sites: list[dict[str, Any]] = []
    models: list[dict[str, Any]] = []
    deps: list[dict[str, Any]] = []
    routing: list[dict[str, Any]] = []
    secrets: list[dict[str, Any]] = []
    log_hints: list[dict[str, Any]] = []
    pii_hints: list[dict[str, Any]] = []
    eval_frameworks: set[str] = set()
    files_with_sites: set[str] = set()

    for path in files:
        rel = path.relative_to(root).as_posix()
        lines = read_lines(path, skipped)
        if lines is None:
            continue
        is_manifest = path.name in MANIFESTS or path.name.startswith("requirements")
        file_sites = 0
        for number, line in enumerate(lines, start=1):
            for provider, kind, rx in SITE_PATTERNS:
                hit = rx.search(line)
                if hit:
                    entry: dict[str, Any] = {
                        "file": rel,
                        "line": number,
                        "provider": provider,
                        "kind": kind,
                        "code": snippet(line),
                    }
                    if kind != "import":
                        block = call_block(lines, number - 1, hit.start())
                        entry["settings_in_call"] = settings_in(block)
                    sites.append(entry)
                    file_sites += 1
            for provider, rx in MODEL_PATTERNS:
                for match in rx.finditer(line):
                    model_id = match.group(0).rstrip(".-:@_")
                    entry = {
                        "id": model_id,
                        "provider": provider,
                        "file": rel,
                        "line": number,
                        "form": model_form(model_id),
                    }
                    for variant in normalize_for_lookup(model_id):
                        if variant in deprecations:
                            entry["lifecycle"] = deprecations[variant]
                            break
                    models.append(entry)
            if ROUTING.search(line):
                routing.append({"file": rel, "line": number, "code": snippet(line)})
            line_secrets = []
            for kind, rx in SECRET_PATTERNS:
                found = rx.search(line)
                if not found:
                    continue
                value = found.group(1) if rx.groups else found.group(0)
                if PLACEHOLDER.search(value):
                    continue
                line_secrets.append(
                    {"file": rel, "line": number, "kind": kind, "starts_with": value[:4] + "..."}
                )
            if len(line_secrets) > 1:  # a specific key shape beats the generic assignment match
                line_secrets = [x for x in line_secrets if x["kind"] != GENERIC_SECRET]
            secrets.extend(line_secrets)
            if is_manifest:
                dep = DEP_RE.search(line)
                if dep:
                    deps.append(
                        {
                            "file": rel,
                            "line": number,
                            "package": dep.group(1),
                            "spec": snippet(dep.group(2)),
                        }
                    )
                for name in EVAL_DEP_RE.findall(line):
                    eval_frameworks.add(name)
        if file_sites:
            files_with_sites.add(rel)
            for number, line in enumerate(lines, start=1):
                if LOG_LINE.search(line):
                    log_hints.append({"file": rel, "line": number, "code": snippet(line)})
                if PII_WORDS.search(line):
                    pii_hints.append({"file": rel, "line": number, "code": snippet(line)})

    distinct = sorted({(m["provider"], m["id"]) for m in models})
    return {
        "root": str(root),
        "scanned_files": len(files),
        "skipped": dict(skipped),
        "files_with_model_calls": sorted(files_with_sites),
        "sites": sites,
        "model_ids": models,
        "distinct_model_ids": [{"provider": p, "id": i} for p, i in distinct],
        "dependencies": deps,
        "routing_hints": routing,
        "secrets_in_files": secrets,
        "tracked_env_files": tracked_env_files(root),
        "logging_hints": log_hints,
        "pii_word_hints": pii_hints,
        "eval_hints": {"files": eval_files, "frameworks": sorted(eval_frameworks)},
        "provider_counts": dict(Counter(s["provider"] for s in sites if s["kind"] != "import")),
        "not_covered": [
            "prompt text kept in databases, CMS or cloud consoles",
            "calls made through a gateway or proxy defined outside this repo",
            "markdown and text documents (only dependency manifests and code are read)",
        ],
    }


def capped(items: list[str], limit: int) -> list[str]:
    shown = [f"  {item}" for item in items[:limit]] or ["  none"]
    if len(items) > limit:
        shown.append(f"  ... {len(items) - limit} more (use --json-out FILE for everything)")
    return shown


def render_text(report: dict[str, Any], limit: int) -> str:
    sites = [s for s in report["sites"] if s["kind"] != "import"]
    models = [
        f"{m['file']}:{m['line']}  {m['provider']} {m['id']} ({m['form']})"
        + (
            f"  LIFECYCLE {m['lifecycle'].get('status')} retires {m['lifecycle'].get('retires')}"
            if m.get("lifecycle")
            else ""
        )
        for m in report["model_ids"]
    ]
    sections: list[tuple[str, list[str]]] = [
        (
            "Call sites (file:line provider kind; settings seen inside the call)",
            [
                f"{s['file']}:{s['line']}  {s['provider']} {s['kind']}  "
                f"[{','.join(s.get('settings_in_call', [])) or '-'}]  {s['code']}"
                for s in sites
            ],
        ),
        ("Model ids", models),
        (
            "Dependencies",
            [f"{d['file']}:{d['line']}  {d['package']}{d['spec']}" for d in report["dependencies"]],
        ),
        (
            "Routing hints (region, endpoint, base url)",
            [f"{d['file']}:{d['line']}  {d['code']}" for d in report["routing_hints"]],
        ),
        (
            "Secrets that look hard-coded (values hidden)",
            [
                f"{d['file']}:{d['line']}  {d['kind']} starting {d['starts_with']}"
                for d in report["secrets_in_files"]
            ],
        ),
        (
            "Log lines that may print prompts or responses",
            [f"{d['file']}:{d['line']}  {d['code']}" for d in report["logging_hints"]],
        ),
        (
            "Words that suggest sensitive data near model code",
            [f"{d['file']}:{d['line']}  {d['code']}" for d in report["pii_word_hints"]],
        ),
        ("Tracked .env files", report["tracked_env_files"]),
    ]
    out = [
        f"Model call inventory for {report['root']}",
        f"{report['scanned_files']} files scanned; skipped: {report['skipped'] or 'nothing'}",
        f"Providers with call or client code: {report['provider_counts'] or 'none found'}",
    ]
    for title, items in sections:
        out += ["", title, *capped(items, limit)]
    evals = report["eval_hints"]
    out += [
        "",
        f"Eval hints: {len(evals['files'])} files by name; frameworks in manifests: "
        f"{evals['frameworks'] or 'none'}",
        *capped(evals["files"], limit),
        "",
        "Not covered by this scan: " + "; ".join(report["not_covered"]),
    ]
    return "\n".join(out)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("root", nargs="?", default=".", type=Path, help="directory to scan")
    parser.add_argument("--json", action="store_true", help="print JSON instead of text")
    parser.add_argument("--json-out", type=Path, help="also write the full JSON to this file")
    parser.add_argument("--deprecations", type=Path, help="JSON of model lifecycle facts")
    parser.add_argument("--limit", type=int, default=80, help="rows per section in text mode")
    args = parser.parse_args(argv)
    try:
        root = args.root.expanduser().resolve()
        if not root.is_dir():
            raise UsageError(f"scan root is not a directory: {root}. Pass the repository path.")
        report = scan(root, load_deprecations(args.deprecations))
    except UsageError as exc:
        print(f"inventory_model_calls: {exc}", file=sys.stderr)
        return 2
    if args.json_out:
        try:
            args.json_out.write_text(json.dumps(report, indent=2), encoding="utf-8")
        except OSError as exc:
            print(f"inventory_model_calls: cannot write {args.json_out}: {exc}", file=sys.stderr)
            return 2
    print(json.dumps(report, indent=2) if args.json else render_text(report, args.limit))
    return 0


if __name__ == "__main__":
    sys.exit(main())
