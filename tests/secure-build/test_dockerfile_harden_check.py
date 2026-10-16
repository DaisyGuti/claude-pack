"""Tests for dockerfile-harden/scripts/dockerfile_check.py on synthetic Dockerfiles."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest

SKILL = (
    Path(__file__).resolve().parents[2]
    / "plugins"
    / "secure-build"
    / "skills"
    / "dockerfile-harden"
)
SPEC = importlib.util.spec_from_file_location(
    "dockerfile_check", SKILL / "scripts" / "dockerfile_check.py"
)
assert SPEC and SPEC.loader
check = importlib.util.module_from_spec(SPEC)
sys.modules["dockerfile_check"] = check
SPEC.loader.exec_module(check)

DIGEST = "sha256:" + "a" * 64
PINNED = f"python:3.13-slim@{DIGEST}"
NONROOT = f"gcr.io/distroless/python3:nonroot@{DIGEST}"


def run(text: str, tmp_path: Path, name: str = "Dockerfile") -> list[str]:
    """Return the rule ids reported for a Dockerfile written to tmp_path."""
    path = tmp_path / name
    path.write_text(text)
    return [f.rule for f in check.check_dockerfile(path, text)]


def findings(text: str, tmp_path: Path) -> list:
    path = tmp_path / "Dockerfile"
    path.write_text(text)
    return check.check_dockerfile(path, text)


GOOD = f"""FROM {PINNED} AS build
RUN pip install --no-cache-dir flask

FROM {NONROOT}
COPY --from=build /usr/local /usr/local
USER 65532:65532
HEALTHCHECK CMD ["python3", "-c", "print(1)"]
ENTRYPOINT ["python3", "-m", "app"]
"""


def test_good_dockerfile_has_no_findings(tmp_path: Path) -> None:
    assert run(GOOD, tmp_path) == []


def test_parse_joins_continuations_and_skips_comments() -> None:
    text = "# header\nRUN apt-get update \\\n  # inner comment\n  && apt-get install -y x\nUSER a\n"
    parsed = check.parse_dockerfile(text)
    assert [(i.name, i.line) for i in parsed] == [("RUN", 2), ("USER", 5)]
    assert "apt-get install" in parsed[0].args


def test_unpinned_base_warns(tmp_path: Path) -> None:
    rules = run("FROM python:3.13-slim\nUSER 1000\n", tmp_path)
    assert "DH001" in rules
    assert "DH002" not in rules


def test_untagged_base_is_error(tmp_path: Path) -> None:
    found = findings("FROM python\nUSER 1000\n", tmp_path)
    assert any(f.rule == "DH002" and f.severity == "error" for f in found)


def test_latest_tag_is_error(tmp_path: Path) -> None:
    found = findings("FROM python:latest\nUSER 1000\n", tmp_path)
    assert any(f.rule == "DH002" and "latest" in f.message for f in found)


def test_scratch_and_earlier_stage_need_no_digest(tmp_path: Path) -> None:
    text = f"FROM {PINNED} AS build\nFROM build AS test\nFROM scratch\nUSER 1000\n"
    assert "DH001" not in run(text, tmp_path)


def test_arg_default_with_digest_passes_and_missing_default_is_info(tmp_path: Path) -> None:
    pinned = f"ARG BASE={PINNED}\nFROM ${{BASE}}\nUSER 1000\n"
    assert "DH001" not in run(pinned, tmp_path)
    unresolved = findings("ARG BASE\nFROM ${BASE}\nUSER 1000\n", tmp_path)
    assert [f.severity for f in unresolved if f.rule == "DH001"] == ["info"]


def test_missing_user_is_error_unless_base_is_nonroot(tmp_path: Path) -> None:
    assert "DH003" in run(f"FROM {PINNED}\n", tmp_path)
    assert "DH003" not in run(f"FROM {NONROOT}\n", tmp_path)


def test_final_user_root_is_error_but_later_user_wins(tmp_path: Path) -> None:
    assert "DH003" in run(f"FROM {PINNED}\nUSER root\n", tmp_path)
    assert "DH003" in run(f"FROM {PINNED}\nUSER 0:0\n", tmp_path)
    assert "DH003" not in run(f"FROM {PINNED}\nUSER root\nRUN true\nUSER 1000\n", tmp_path)


def test_single_stage_compile_is_info(tmp_path: Path) -> None:
    text = f"FROM {PINNED}\nRUN make all\nUSER 1000\n"
    assert "DH004" in run(text, tmp_path)
    multi = f"FROM {PINNED} AS build\nRUN make all\nFROM {PINNED}\nUSER 1000\n"
    assert "DH004" not in run(multi, tmp_path)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("ADD app.py /app/", True),
        ("ADD rootfs.tar.gz /", False),
        ("ADD https://example.com/x.bin /x", True),
        (f"ADD --checksum={DIGEST} https://example.com/x.bin /x", False),
        ("COPY app.py /app/", False),
    ],
)
def test_add_rules(tmp_path: Path, line: str, expected: bool) -> None:
    assert ("DH005" in run(f"FROM {PINNED}\n{line}\nUSER 1000\n", tmp_path)) is expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("ENV DB_PASSWORD=hunter2", True),
        ("ENV DB_PASSWORD hunter2", True),
        ("ENV API_TOKEN=$API_TOKEN", False),
        ("ENV LOG_LEVEL=info", False),
        ("ARG NPM_TOKEN", True),
        ("ARG VERSION=1", False),
    ],
)
def test_secret_in_env_or_arg(tmp_path: Path, line: str, expected: bool) -> None:
    assert ("DH006" in run(f"FROM {PINNED}\n{line}\nUSER 1000\n", tmp_path)) is expected


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("COPY .env /app/.env", True),
        ("COPY .env.example /app/", False),
        ("COPY certs/server.pem /etc/", True),
        ("COPY id_rsa /root/.ssh/", True),
        ("COPY --from=build /out/.env /app/", False),
        ("COPY src/ /app/", False),
    ],
)
def test_sensitive_file_copy(tmp_path: Path, line: str, expected: bool) -> None:
    assert ("DH007" in run(f"FROM {PINNED}\n{line}\nUSER 1000\n", tmp_path)) is expected


def test_pipe_to_shell(tmp_path: Path) -> None:
    text = f"FROM {PINNED}\nRUN curl -fsSL https://x.example/install.sh | sh\nUSER 1000\n"
    assert "DH008" in run(text, tmp_path)
    safe = f"FROM {PINNED}\nRUN curl -fsSL -o /tmp/i.sh https://x.example/i.sh\nUSER 1000\n"
    assert "DH008" not in run(safe, tmp_path)


@pytest.mark.parametrize(
    ("run_line", "expected_count"),
    [
        ("apt-get update && apt-get install -y curl", 2),
        (
            "apt-get update && apt-get install -y --no-install-recommends curl "
            "&& rm -rf /var/lib/apt/lists/*",
            0,
        ),
        ("apt-get update", 1),
        ("apk add curl", 1),
        ("apk add --no-cache curl", 0),
        ("sudo make install", 1),
        ("apt-get dist-upgrade -y", 1),
    ],
)
def test_package_manager_hygiene(tmp_path: Path, run_line: str, expected_count: int) -> None:
    rules = run(f"FROM {PINNED}\nRUN {run_line}\nUSER 1000\n", tmp_path)
    assert rules.count("DH009") == expected_count


def test_healthcheck_info_when_missing(tmp_path: Path) -> None:
    assert "DH010" in run(f"FROM {PINNED}\nUSER 1000\n", tmp_path)
    assert "DH010" not in run(f"FROM {PINNED}\nUSER 1000\nHEALTHCHECK CMD true\n", tmp_path)


@pytest.mark.parametrize(
    ("line", "expected"),
    [
        ("RUN chmod 777 /data", True),
        ("RUN chmod -R a+rwx /data", True),
        ("RUN chmod u+s /bin/x", True),
        ("RUN chmod 4755 /bin/x", True),
        ("RUN chmod 755 /data", False),
        ("EXPOSE 22", True),
        ("EXPOSE 8080", False),
    ],
)
def test_permission_rules(tmp_path: Path, line: str, expected: bool) -> None:
    assert ("DH011" in run(f"FROM {PINNED}\n{line}\nUSER 1000\n", tmp_path)) is expected


def test_shell_form_cmd(tmp_path: Path) -> None:
    assert "DH012" in run(f"FROM {PINNED}\nUSER 1000\nCMD python app.py\n", tmp_path)
    assert "DH012" not in run(f'FROM {PINNED}\nUSER 1000\nCMD ["python", "app.py"]\n', tmp_path)


def test_dockerignore_required_for_broad_copy(tmp_path: Path) -> None:
    text = f"FROM {PINNED}\nCOPY . /app\nUSER 1000\n"
    assert "DH013" in run(text, tmp_path)
    (tmp_path / ".dockerignore").write_text(".git\n")
    assert "DH013" not in run(text, tmp_path)


def test_credentials_in_url(tmp_path: Path) -> None:
    text = f"FROM {PINNED}\nRUN git clone https://user:pass@example.com/r.git\nUSER 1000\n"
    assert "DH014" in run(text, tmp_path)


def test_no_from_is_reported(tmp_path: Path) -> None:
    assert run("RUN echo hi\n", tmp_path) == ["DH000"]


# ---------------------------------------------------------------- Compose

BAD_COMPOSE = """services:
  web:
    image: nginx:latest
    privileged: true
    network_mode: host
    cap_add:
      - SYS_ADMIN
      - NET_RAW
    security_opt:
      - seccomp:unconfined
    volumes:
      - /var/run/docker.sock:/var/run/docker.sock
    ports:
      - "8080:8080"
    environment:
      DB_PASSWORD: hunter2
  worker:
    image: ghcr.io/example/worker:1.0@sha256:{digest}
    user: "1000:1000"
    read_only: true
    cap_drop: [ALL]
    security_opt: ["no-new-privileges:true"]
    pids_limit: 100
    healthcheck:
      test: ["CMD", "true"]
"""


def compose_findings(text: str, tmp_path: Path) -> list:
    path = tmp_path / "compose.yaml"
    path.write_text(text)
    return check.check_compose(path, text)


def test_bad_compose_service_triggers_each_rule(tmp_path: Path) -> None:
    found = compose_findings(BAD_COMPOSE.format(digest="b" * 64), tmp_path)
    web = {f.rule for f in found if f.message.startswith("[web]")}
    assert {
        "DC001", "DC002", "DC003", "DC004", "DC005", "DC006", "DC007",
        "DC008", "DC009", "DC010", "DC011", "DC012", "DC013",
    } <= web  # fmt: skip
    errors = {f.rule for f in found if f.severity == "error" and f.message.startswith("[web]")}
    assert {"DC001", "DC002", "DC003", "DC004", "DC007"} <= errors


def test_hardened_service_in_same_file_is_clean(tmp_path: Path) -> None:
    found = compose_findings(BAD_COMPOSE.format(digest="b" * 64), tmp_path)
    assert [f for f in found if f.message.startswith("[worker]")] == []


def test_cap_add_net_raw_is_warning_not_error(tmp_path: Path) -> None:
    found = compose_findings(BAD_COMPOSE.format(digest="b" * 64), tmp_path)
    caps = {f.message: f.severity for f in found if f.rule == "DC004"}
    assert caps["[web] cap_add grants SYS_ADMIN."] == "error"
    assert caps["[web] cap_add grants NET_RAW."] == "warning"


def test_secret_file_reference_is_not_a_literal(tmp_path: Path) -> None:
    text = "services:\n  a:\n    environment:\n      DB_PASSWORD_FILE: /run/secrets/db\n"
    assert "DC011" not in {f.rule for f in compose_findings(text, tmp_path)}


def test_compose_without_services(tmp_path: Path) -> None:
    assert [f.rule for f in compose_findings("version: '3'\n", tmp_path)] == ["DC000"]


# ---------------------------------------------------------------- Templates and CLI


def test_shipped_templates_have_no_warning_or_error() -> None:
    found = check.run([SKILL / "templates"])
    assert [f.text() for f in found if f.severity != "info"] == []


def test_discover_finds_dockerfiles_and_compose_in_a_directory(tmp_path: Path) -> None:
    (tmp_path / "svc").mkdir()
    (tmp_path / "svc" / "Dockerfile").write_text(GOOD)
    (tmp_path / "svc" / "api.Dockerfile").write_text(GOOD)
    (tmp_path / "docker-compose.prod.yml").write_text("services: {}\n")
    (tmp_path / "notes.txt").write_text("x")
    names = sorted(p.name for p in check.discover([tmp_path]))
    assert names == ["Dockerfile", "api.Dockerfile", "docker-compose.prod.yml"]


def test_cli_exit_codes(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    good = tmp_path / "Dockerfile"
    good.write_text(GOOD)
    assert check.main([str(good)]) == 0
    bad = tmp_path / "bad.Dockerfile"
    bad.write_text("FROM python\n")
    assert check.main([str(bad)]) == 1
    assert check.main(["--fail-on", "error", str(bad)]) == 1
    warn_only = tmp_path / "warn.Dockerfile"
    warn_only.write_text("FROM python:3.13\nUSER 1000\nHEALTHCHECK CMD true\n")
    assert check.main([str(warn_only)]) == 1
    assert check.main(["--fail-on", "error", str(warn_only)]) == 0
    capsys.readouterr()


def test_cli_missing_path_exits_two_with_a_fix(capsys: pytest.CaptureFixture[str]) -> None:
    assert check.main(["/nonexistent/Dockerfile"]) == 2
    err = capsys.readouterr().err
    assert "/nonexistent/Dockerfile" in err
    assert "Pass a Dockerfile" in err


def test_cli_json_output(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    bad = tmp_path / "Dockerfile"
    bad.write_text("FROM python\n")
    check.main(["--json", str(bad)])
    data = json.loads(capsys.readouterr().out)
    assert {"path", "line", "rule", "severity", "message", "fix"} <= set(data[0])
    assert any(item["rule"] == "DH002" for item in data)
