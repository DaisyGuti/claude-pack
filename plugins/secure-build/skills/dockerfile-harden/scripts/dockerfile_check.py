#!/usr/bin/env python3
"""Check Dockerfiles and Compose files for the obvious hardening gaps.

Usage:
    dockerfile_check.py [--json] [--fail-on info|warning|error] PATH [PATH ...]

PATH is a Dockerfile, a Compose file, or a directory (searched recursively for both).
Exit codes: 0 no finding at or above --fail-on, 1 at least one, 2 bad input.

The checks are line-based and heuristic. They find what a reader can see in the text and
say "cannot verify" for anything that depends on a build argument or a base image's
metadata. hadolint and dockle (see SKILL.md) are the fuller linters; this script runs
with the standard library alone so it works where neither is installed.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from pathlib import Path

SEVERITIES = ("info", "warning", "error")

DIGEST = re.compile(r"@sha256:[0-9a-f]{64}")
SECRET_NAME = re.compile(
    r"(pass(word|wd)?|secret|token|api[_-]?key|private[_-]?key|credential)", re.IGNORECASE
)
SENSITIVE_FILE = re.compile(
    r"(^|/)(\.env(?!\.(example|sample|template))|id_rsa|id_ed25519|\.npmrc|\.pypirc|\.netrc"
    r"|\.git-credentials|\.aws|kubeconfig|credentials\.json|service[-_]account[^/\s]*\.json)"
    r"|\.(pem|key|p12|pfx)(\s|$)",
    re.IGNORECASE,
)
PIPE_TO_SHELL = re.compile(r"\b(curl|wget)\b[^|;&\n]*\|\s*(sudo\s+)?(ba|z|da)?sh\b")
URL_CREDENTIALS = re.compile(r"://[^/\s:@]+:[^/\s@]+@")
ARCHIVE = re.compile(r"\.(tar|tgz|tar\.gz|tar\.bz2|tar\.xz|txz)$", re.IGNORECASE)
DANGEROUS_CAPS = {"ALL", "SYS_ADMIN", "SYS_MODULE", "SYS_PTRACE", "SYS_RAWIO"}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str
    severity: str
    message: str
    fix: str

    def text(self) -> str:
        return (
            f"{self.path}:{self.line}: {self.rule} {self.severity}: {self.message} Fix: {self.fix}"
        )


# ---------------------------------------------------------------- Dockerfile parsing


@dataclass
class Instruction:
    line: int
    name: str
    args: str


def parse_dockerfile(text: str) -> list[Instruction]:
    """Join backslash continuations, drop comments and blank lines."""
    instructions: list[Instruction] = []
    buffer = ""
    start = 0
    for number, raw in enumerate(text.splitlines(), start=1):
        stripped = raw.strip()
        if not buffer and (not stripped or stripped.startswith("#")):
            continue
        if stripped.startswith("#"):
            continue  # a comment line inside a continued instruction
        if not buffer:
            start = number
        if stripped.endswith("\\"):
            buffer += stripped[:-1] + " "
            continue
        buffer += stripped
        name, _, args = buffer.partition(" ")
        instructions.append(Instruction(start, name.upper(), args.strip()))
        buffer = ""
    if buffer:
        name, _, args = buffer.partition(" ")
        instructions.append(Instruction(start, name.upper(), args.strip()))
    return instructions


@dataclass
class Stage:
    line: int
    base: str
    name: str
    instructions: list[Instruction]


def split_stages(instructions: list[Instruction]) -> tuple[dict[str, str], list[Stage]]:
    """Return the ARG defaults declared before the first FROM, and the stages."""
    global_args: dict[str, str] = {}
    stages: list[Stage] = []
    for ins in instructions:
        if ins.name == "FROM":
            words = [w for w in ins.args.split() if not w.startswith("--")]
            base = words[0] if words else ""
            alias = words[2] if len(words) >= 3 and words[1].upper() == "AS" else ""
            stages.append(Stage(ins.line, base, alias, []))
        elif not stages:
            if ins.name == "ARG" and "=" in ins.args:
                key, _, value = ins.args.partition("=")
                global_args[key.strip()] = value.strip().strip("\"'")
        else:
            stages[-1].instructions.append(ins)
    return global_args, stages


def resolve_base(base: str, global_args: dict[str, str]) -> str | None:
    """Substitute ${VAR} / $VAR from ARG defaults; None when a variable has no default."""

    def sub(match: re.Match[str]) -> str:
        key = match.group(1) or match.group(2)
        return global_args.get(key, match.group(0))

    resolved = re.sub(r"\$\{(\w+)(?::-[^}]*)?\}|\$(\w+)", sub, base)
    return None if "$" in resolved else resolved


def has_tag(image: str) -> bool:
    return ":" in image.rsplit("/", 1)[-1]


def check_dockerfile(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    shown = str(path)

    def add(line: int, rule: str, severity: str, message: str, fix: str) -> None:
        findings.append(Finding(shown, line, rule, severity, message, fix))

    instructions = parse_dockerfile(text)
    global_args, stages = split_stages(instructions)
    if not stages:
        add(1, "DH000", "error", "No FROM instruction found.", "Check that this is a Dockerfile.")
        return findings

    for index, stage in enumerate(stages):
        earlier = {s.name.lower() for s in stages[:index] if s.name}
        if stage.base.lower() == "scratch" or stage.base.lower() in earlier:
            continue
        image = resolve_base(stage.base, global_args)
        if image is None:
            add(
                stage.line,
                "DH001",
                "info",
                f"Base image '{stage.base}' depends on a build argument with no default, so "
                "the digest pin cannot be verified.",
                "Give the ARG a default that includes @sha256:<digest>.",
            )
            continue
        if not DIGEST.search(image):
            add(
                stage.line,
                "DH001",
                "warning",
                f"Base image '{image}' is not pinned by digest.",
                "Pin as image:tag@sha256:<digest> (resolve with `docker buildx imagetools "
                "inspect`) and let Renovate or Dependabot move the pin.",
            )
            if not has_tag(image):
                add(
                    stage.line,
                    "DH002",
                    "error",
                    f"Base image '{image}' has no tag, which means latest (hadolint DL3006).",
                    "Name an explicit version tag next to the digest.",
                )
            elif image.endswith(":latest"):
                add(
                    stage.line,
                    "DH002",
                    "error",
                    f"Base image '{image}' uses the latest tag (hadolint DL3007).",
                    "Name an explicit version tag next to the digest.",
                )

    final = stages[-1]
    final_image = resolve_base(final.base, global_args) or final.base

    # Which user does the final stage run as?
    users = [i for i in final.instructions if i.name == "USER"]
    if not users:
        if "nonroot" not in final_image.lower() and final_image.lower() != "scratch":
            add(
                final.line,
                "DH003",
                "error",
                "The final stage has no USER instruction, so it runs as root unless the base "
                "image sets another user (dockle CIS-DI-0001).",
                "Add USER with a numeric non-root id, or use a :nonroot base image.",
            )
    else:
        last = users[-1]
        if last.args.split(":")[0].strip().lower() in {"root", "0"}:
            add(
                last.line,
                "DH003",
                "error",
                "The final USER is root (hadolint DL3002, dockle CIS-DI-0001).",
                "Switch to a numeric non-root id before CMD or ENTRYPOINT.",
            )

    if len(stages) == 1 and any(
        i.name == "RUN"
        and re.search(
            r"\b(gcc|g\+\+|make|go build|cargo build|mvn|gradle|npm run build|build-essential)\b",
            i.args,
        )
        for i in final.instructions
    ):
        add(
            final.line,
            "DH004",
            "info",
            "Single-stage build that compiles code: compilers and caches stay in the image.",
            "Split into a build stage and a minimal runtime stage with COPY --from.",
        )

    if not any(i.name == "HEALTHCHECK" for i in final.instructions):
        add(
            final.line,
            "DH010",
            "info",
            "The final stage has no HEALTHCHECK (dockle CIS-DI-0006). Kubernetes and Cloud Run "
            "ignore it and use probes instead.",
            "Add HEALTHCHECK in exec form, or define a probe in the deployment.",
        )

    for stage in stages:
        for ins in stage.instructions:
            findings.extend(_check_instruction(shown, ins))

    if any(
        i.name in {"COPY", "ADD"}
        and any(tok in {".", "./", "*"} for tok in _sources(i.args))
        and "--from=" not in i.args
        for stage in stages
        for i in stage.instructions
    ):
        sibling = path.with_name(path.name + ".dockerignore")
        if not (path.with_name(".dockerignore").exists() or sibling.exists()):
            add(
                1,
                "DH013",
                "warning",
                "The build copies the whole context but no .dockerignore sits next to the "
                "Dockerfile, so .git, .env files and local keys can enter the image.",
                "Add a .dockerignore (see templates/dockerignore).",
            )

    final_cmds = [i for i in final.instructions if i.name in {"CMD", "ENTRYPOINT"}]
    for ins in final_cmds:
        if not ins.args.lstrip().startswith("["):
            add(
                ins.line,
                "DH012",
                "info",
                f"{ins.name} uses shell form: a shell becomes PID 1 and swallows signals "
                "(hadolint DL3025).",
                "Use exec form: " + ins.name + ' ["binary", "arg"].',
            )

    return findings


def _sources(args: str) -> list[str]:
    words = [w for w in args.split() if not w.startswith("--")]
    return words[:-1] if len(words) > 1 else []


def _check_instruction(shown: str, ins: Instruction) -> list[Finding]:
    out: list[Finding] = []

    def add(rule: str, severity: str, message: str, fix: str) -> None:
        out.append(Finding(shown, ins.line, rule, severity, message, fix))

    if URL_CREDENTIALS.search(ins.args):
        add(
            "DH014",
            "error",
            "A URL with embedded credentials is written into the Dockerfile.",
            "Remove it and use RUN --mount=type=secret or a credential helper.",
        )

    if ins.name in {"ENV", "ARG"}:
        for key, value in _env_pairs(ins):
            if not SECRET_NAME.search(key):
                continue
            if value and not value.startswith("$"):
                add(
                    "DH006",
                    "error",
                    f"{ins.name} {key} stores a secret-looking value in the image "
                    "(dockle CIS-DI-0010).",
                    "Remove it. Pass it at build time with --secret and use "
                    "RUN --mount=type=secret,id=...; pass it at run time from the platform.",
                )
            elif ins.name == "ARG":
                add(
                    "DH006",
                    "warning",
                    f"ARG {key} looks like a secret; build arguments remain in image history.",
                    "Use RUN --mount=type=secret instead of a build argument.",
                )

    if ins.name in {"COPY", "ADD"} and "--from=" not in ins.args:
        for source in _sources(ins.args):
            if SENSITIVE_FILE.search(source + " "):
                add(
                    "DH007",
                    "error",
                    f"{ins.name} copies '{source}', which looks like a credential or key file.",
                    "Exclude it in .dockerignore and supply it with a build secret mount.",
                )

    if ins.name == "ADD" and "--from=" not in ins.args:
        sources = _sources(ins.args)
        is_url = any(s.startswith(("http://", "https://")) for s in sources)
        if is_url and "--checksum=" not in ins.args:
            add(
                "DH005",
                "warning",
                "ADD fetches a URL without --checksum.",
                "Add --checksum=sha256:<digest> or download in a build stage and verify.",
            )
        elif not is_url and not all(ARCHIVE.search(s) for s in sources):
            add(
                "DH005",
                "warning",
                "ADD used where COPY is enough (hadolint DL3020, dockle CIS-DI-0009).",
                "Use COPY; keep ADD for extracting a local tar archive.",
            )

    if ins.name == "RUN":
        args = ins.args
        if PIPE_TO_SHELL.search(args):
            add(
                "DH008",
                "error",
                "A downloaded script is piped straight into a shell.",
                "Download to a file, verify its checksum or signature, then run it.",
            )
        if re.search(r"\bapt-get\b.*\binstall\b", args):
            if "--no-install-recommends" not in args:
                add(
                    "DH009",
                    "warning",
                    "apt-get install without --no-install-recommends (hadolint DL3015).",
                    "Add --no-install-recommends.",
                )
            if "/var/lib/apt/lists" not in args:
                add(
                    "DH009",
                    "warning",
                    "apt-get install without removing /var/lib/apt/lists in the same RUN "
                    "(hadolint DL3009, dockle DKL-DI-0005).",
                    "End the RUN with rm -rf /var/lib/apt/lists/*.",
                )
        if re.search(r"\bapt-get\s+update\b", args) and not re.search(r"\binstall\b", args):
            add(
                "DH009",
                "warning",
                "apt-get update on its own line caches a stale index (dockle CIS-DI-0007).",
                "Run update and install in one RUN.",
            )
        if re.search(r"\bapt-get\s+dist-upgrade\b", args):
            add(
                "DH009",
                "warning",
                "apt-get dist-upgrade changes the base image unpredictably (dockle DKL-DI-0003).",
                "Pick a newer base digest instead.",
            )
        if re.search(r"\bapk\s+add\b", args) and "--no-cache" not in args:
            add(
                "DH009",
                "warning",
                "apk add without --no-cache (hadolint DL3019, dockle DKL-DI-0004).",
                "Add --no-cache.",
            )
        if re.search(r"\bsudo\b", args):
            add(
                "DH009",
                "error",
                "sudo inside a Dockerfile (hadolint DL3004, dockle DKL-DI-0001).",
                "Run the step as root before the final USER, or use a build stage.",
            )
        if re.search(r"chmod\s+(-R\s+)?(0?777|a\+rwx|[ugo]*\+s)\b", args) or re.search(
            r"chmod\s+(-R\s+)?[0-9]?[2467][0-7]{3}\b", args
        ):
            add(
                "DH011",
                "warning",
                "chmod grants world-write or sets setuid/setgid (dockle CIS-DI-0008).",
                "Grant the narrowest mode, usually 0555 for files and 0755 for directories.",
            )

    if ins.name == "EXPOSE" and re.search(r"(^|\s)22(/|\s|$)", ins.args):
        add("DH011", "warning", "EXPOSE 22 suggests an SSH server in the image.", "Remove sshd.")

    return out


def _env_pairs(ins: Instruction) -> list[tuple[str, str]]:
    args = ins.args
    if "=" not in args and ins.name == "ENV":
        key, _, value = args.partition(" ")
        return [(key, value.strip().strip("\"'"))]
    pairs: list[tuple[str, str]] = []
    for token in re.findall(r"""[^\s=]+=(?:"[^"]*"|'[^']*'|\S*)|\S+""", args):
        key, _, value = token.partition("=")
        pairs.append((key, value.strip("\"'")))
    return pairs


# ---------------------------------------------------------------- Compose parsing


def _indent(line: str) -> int:
    return len(line) - len(line.lstrip(" "))


def split_services(text: str) -> dict[str, tuple[int, list[tuple[int, str]]]]:
    """Map service name -> (line number, [(line number, line), ...]) from a Compose file."""
    lines = text.splitlines()
    services: dict[str, tuple[int, list[tuple[int, str]]]] = {}
    in_services = False
    child_indent: int | None = None
    current: str | None = None
    for number, line in enumerate(lines, start=1):
        stripped = line.strip()
        if not stripped or stripped.startswith("#"):
            continue
        if _indent(line) == 0:
            in_services = stripped.startswith("services:")
            current = None
            continue
        if not in_services:
            continue
        if child_indent is None:
            child_indent = _indent(line)
        if _indent(line) == child_indent and stripped.endswith(":"):
            current = stripped[:-1].strip("\"'")
            services[current] = (number, [])
        elif current is not None:
            services[current][1].append((number, line))
    return services


def _value(block: list[tuple[int, str]], key: str) -> tuple[int, str] | None:
    pattern = re.compile(rf"^\s*{re.escape(key)}:\s*(.*?)\s*(#.*)?$")
    for number, line in block:
        match = pattern.match(line)
        if match:
            return number, match.group(1).strip("\"'")
    return None


def _list_after(block: list[tuple[int, str]], key: str) -> list[tuple[int, str]]:
    """Items of a YAML list under `key:`, either inline [a, b] or as '- item' lines."""
    for index, (number, line) in enumerate(block):
        match = re.match(rf"^(\s*){re.escape(key)}:\s*(.*?)\s*$", line)
        if not match:
            continue
        inline = match.group(2)
        if inline.startswith("["):
            return [(number, v.strip().strip("\"'")) for v in inline.strip("[]").split(",") if v]
        items: list[tuple[int, str]] = []
        base = len(match.group(1))
        for later_number, later in block[index + 1 :]:
            if later.strip().startswith("#"):
                continue
            if later.strip().startswith("- ") and _indent(later) >= base:
                items.append((later_number, later.strip()[2:].strip().strip("\"'")))
            elif later.strip() and _indent(later) <= base:
                break
        return items
    return []


def check_compose(path: Path, text: str) -> list[Finding]:
    findings: list[Finding] = []
    shown = str(path)
    services = split_services(text)
    if not services:
        return [
            Finding(
                shown,
                1,
                "DC000",
                "info",
                "No services found in this Compose file.",
                "Check the file path and indentation.",
            )
        ]
    for name, (start, block) in services.items():

        def add(
            line: int, rule: str, severity: str, message: str, fix: str, svc: str = name
        ) -> None:
            findings.append(Finding(shown, line, rule, severity, f"[{svc}] {message}", fix))

        privileged = _value(block, "privileged")
        if privileged and privileged[1].lower() == "true":
            add(
                privileged[0],
                "DC001",
                "error",
                "privileged: true gives the container nearly all host capabilities.",
                "Remove it. Add only the single capability the process needs with cap_add.",
            )
        for key in ("network_mode", "pid", "ipc", "userns_mode"):
            found = _value(block, key)
            if found and found[1].lower() == "host":
                add(
                    found[0],
                    "DC002",
                    "error",
                    f"{key}: host shares a host namespace with the container.",
                    "Use the default isolated namespace and publish only the ports needed.",
                )
        for number, line in block:
            if "docker.sock" in line:
                add(
                    number,
                    "DC003",
                    "error",
                    "The Docker socket is mounted: the container can control the host daemon.",
                    "Remove the mount, or put a socket proxy with a narrow allowlist in front.",
                )
        added = _list_after(block, "cap_add")
        for number, cap in added:
            cap_name = cap.upper().removeprefix("CAP_")
            add(
                number,
                "DC004",
                "error" if cap_name in DANGEROUS_CAPS else "warning",
                f"cap_add grants {cap}.",
                "Drop ALL capabilities and add back only what the process proves it needs.",
            )
        drops = {c.upper() for _, c in _list_after(block, "cap_drop")}
        if "ALL" not in drops:
            add(
                start,
                "DC005",
                "warning",
                "cap_drop does not include ALL.",
                "Add cap_drop: [ALL].",
            )
        read_only = _value(block, "read_only")
        if not read_only or read_only[1].lower() != "true":
            add(
                start,
                "DC006",
                "warning",
                "The root filesystem is writable.",
                "Add read_only: true and mount tmpfs for the paths that must be written.",
            )
        security_opts = [o.lower().replace("=", ":") for _, o in _list_after(block, "security_opt")]
        if (
            "no-new-privileges:true" not in security_opts
            and "no-new-privileges" not in security_opts
        ):
            add(
                start,
                "DC007",
                "warning",
                "security_opt does not set no-new-privileges.",
                "Add security_opt: [no-new-privileges:true].",
            )
        for number, opt in _list_after(block, "security_opt"):
            if "unconfined" in opt.lower():
                add(
                    number,
                    "DC007",
                    "error",
                    f"security_opt '{opt}' turns off a kernel confinement profile.",
                    "Remove it and fix the syscall or profile the process needs.",
                )
        image = _value(block, "image")
        if image and image[1]:
            ref = image[1]
            if not DIGEST.search(ref):
                add(
                    image[0],
                    "DC008",
                    "warning",
                    f"image '{ref}' is not pinned by digest.",
                    "Pin as image:tag@sha256:<digest>.",
                )
            if not has_tag(ref) or ref.endswith(":latest"):
                add(
                    image[0],
                    "DC008",
                    "warning",
                    f"image '{ref}' has no version tag or uses latest.",
                    "Name an explicit version tag.",
                )
        user = _value(block, "user")
        if not user or user[1].split(":")[0] in {"root", "0", ""}:
            add(
                user[0] if user else start,
                "DC009",
                "warning",
                "No non-root user is set for this service.",
                "Add user: '10001:10001' (a numeric id the image does not need to define).",
            )
        for number, port in _list_after(block, "ports"):
            if not port.startswith(("127.0.0.1:", "[::1]:", "localhost:")):
                add(
                    number,
                    "DC010",
                    "info",
                    f"Port '{port}' is published on all host interfaces.",
                    "Bind to 127.0.0.1 unless the service must be reachable from the network.",
                )
        for number, line in block:
            match = re.match(r"^\s*-?\s*([A-Za-z0-9_]+)\s*[:=]\s*(.+?)\s*$", line)
            if (
                match
                and SECRET_NAME.search(match.group(1))
                and not match.group(1).upper().endswith("_FILE")
                and not match.group(2).startswith(("$", "{", "[", "#"))
                and match.group(1).upper() == match.group(1)
            ):
                add(
                    number,
                    "DC011",
                    "warning",
                    f"{match.group(1)} holds a literal secret-looking value.",
                    "Use Compose secrets, or resolve the value from outside the file.",
                )
        if not _value(block, "healthcheck"):
            add(
                start,
                "DC012",
                "info",
                "No healthcheck defined.",
                "Add a healthcheck so orchestration can restart a wedged process.",
            )
        if not any(_value(block, k) for k in ("pids_limit", "mem_limit", "cpus")) and not any(
            "limits:" in line for _, line in block
        ):
            add(
                start,
                "DC013",
                "info",
                "No process, memory or CPU limit.",
                "Set pids_limit and mem_limit (or deploy.resources.limits).",
            )
    return findings


# ---------------------------------------------------------------- Discovery and CLI


def is_compose(path: Path) -> bool:
    return bool(re.fullmatch(r"(docker-)?compose(\.[\w-]+)?\.ya?ml", path.name, re.IGNORECASE))


def is_dockerfile(path: Path) -> bool:
    name = path.name.lower()
    return name == "dockerfile" or name.startswith("dockerfile.") or name.endswith(".dockerfile")


def discover(paths: list[Path]) -> list[Path]:
    found: list[Path] = []
    for path in paths:
        if path.is_dir():
            found.extend(
                sorted(
                    p
                    for p in path.rglob("*")
                    if p.is_file() and (is_dockerfile(p) or is_compose(p)) and ".git" not in p.parts
                )
            )
        elif path.is_file():
            found.append(path)
        else:
            raise FileNotFoundError(
                f"{path}: no such file or directory. Pass a Dockerfile, a "
                "Compose file or a directory."
            )
    return found


def run(paths: list[Path]) -> list[Finding]:
    findings: list[Finding] = []
    for path in discover(paths):
        text = path.read_text(encoding="utf-8", errors="replace")
        findings.extend(
            check_compose(path, text) if is_compose(path) else check_dockerfile(path, text)
        )
    return findings


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0] if __doc__ else "")
    parser.add_argument("paths", nargs="+", type=Path)
    parser.add_argument("--json", action="store_true", help="print findings as JSON")
    parser.add_argument("--fail-on", choices=SEVERITIES, default="warning")
    args = parser.parse_args(argv)
    try:
        findings = run(args.paths)
    except (FileNotFoundError, OSError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps([asdict(f) for f in findings], indent=2))
    else:
        for finding in findings:
            print(finding.text())
        if not findings:
            print("No findings in the text-level checks. A built image needs dockle and a scan.")
    threshold = SEVERITIES.index(args.fail_on)
    return 1 if any(SEVERITIES.index(f.severity) >= threshold for f in findings) else 0


if __name__ == "__main__":
    sys.exit(main())
