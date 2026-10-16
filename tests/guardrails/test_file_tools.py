"""Write, Edit, MultiEdit, NotebookEdit, Read and Grep calls."""

from __future__ import annotations

import pytest

# Credential-shaped values built from parts, so this file holds no literal a scanner would flag.
GITHUB = "gh" + "p_" + "a1B2c3D4e5F6" * 3
GITHUB_FINE = "github" + "_pat_" + "11ABCDEFG0" + "abcdefghij" + "_ABCDEFGHIJ" + "klmnop"
GITLAB = "gl" + "pat-" + "AbCdEfGhIjKlMnOpQrSt"
SLACK = "xo" + "xb-" + "1234567890-abcdefghijkl"
SLACK_APP = "xa" + "pp-1-A0123456789-1234567890-" + "abcdef0123456789"
SLACK_HOOK = (
    "https://hooks.slack" + ".com/services/T01234567/B01234567/" + "abcdefghijklmnopqrstuvwx"
)
AWS = "AK" + "IA" + "QWERTYUIOPASDFGH"
AWS_SECRET = 'aws_secret_access_key = "' + "wJalrXUtnFEMI/K7MDENG/bPxRfiCY" + 'QWERTYUIOP12"'
GOOGLE_KEY = "AI" + "za" + "SyA-1234567890abcdefghijklmnopqrstu"
GOOGLE_SECRET = "GOC" + "SPX-" + "abcdefghijklmnopqrstuvwxyz12"
ANTHROPIC = "sk-" + "ant-" + "api03-abcdefghijklmnopqrstuvwx"
PEM_BODY = "MIIEvQIBADANBgkqhkiG9w0BAQEFAASCBKcwggSjAgEAAoIBAQC7VJTUt9Us8cKj"
PRIVATE_KEY = "-----BEGIN " + "PRIVATE KEY-----\n" + PEM_BODY + "\n-----END PRIVATE KEY-----\n"
OPENSSH_KEY = "-----BEGIN OPENSSH " + "PRIVATE KEY-----\n" + PEM_BODY + "\n"
SA_JSON = (
    '{"type": "service_account", "project_id": "p", "private_key_id": "abc123",\n'
    ' "private_key": "-----BEGIN '
    + "PRIVATE KEY-----\\n"
    + PEM_BODY
    + '\\n-----END PRIVATE KEY-----\\n",\n'
    ' "client_email": "sa@p.iam.gserviceaccount.com"}\n'
)
SA_JSON_NO_BEGIN = '{"type": "service_account", "private_key_id": "abc123", "private_key": "x"}'
RANDOM_VALUE = "Zk3Jf9aQw2LmN8pXr5Tv7Bc1"

SECRET_CONTENT = [
    ("private key block", PRIVATE_KEY),
    ("openssh private key", OPENSSH_KEY),
    ("GCP service account key JSON", SA_JSON),
    ("GCP service account JSON, key id only", SA_JSON_NO_BEGIN),
    ("AWS access key id", f'AWS_ACCESS_KEY_ID = "{AWS}"\n'),
    ("AWS secret access key", AWS_SECRET + "\n"),
    ("GitHub classic token", f"token: {GITHUB}\n"),
    ("GitHub fine-grained token", f"export GH={GITHUB_FINE}\n"),
    ("GitLab token", f"CI_TOKEN={GITLAB}\n"),
    ("Slack bot token", f'SLACK = "{SLACK}"\n'),
    ("Slack app token", f"{SLACK_APP}\n"),
    ("Slack webhook", f"url = '{SLACK_HOOK}'\n"),
    ("Google API key", f'key: "{GOOGLE_KEY}"\n'),
    ("Google OAuth client secret", f"client_secret: {GOOGLE_SECRET}\n"),
    ("Anthropic key", f"KEY={ANTHROPIC}\n"),
    ("generic _SECRET", f"APP_SECRET={RANDOM_VALUE}\n"),
    ("generic _TOKEN quoted", f'API_TOKEN = "{RANDOM_VALUE}"\n'),
    ("generic password in yaml", f"db_password: {RANDOM_VALUE}\n"),
    ("generic json", f'{{"apiKey": "{RANDOM_VALUE}"}}\n'),
    ("generic export", f"export STRIPE_SECRET_KEY={RANDOM_VALUE}\n"),
    ("secret in the middle of a file", "a = 1\n" * 20 + f"AUTH_TOKEN={RANDOM_VALUE}\n" + "b = 2\n"),
]

SAFE_CONTENT = [
    ("plain code", "def add(a, b):\n    return a + b\n"),
    ("env read", 'TOKEN = os.environ["API_TOKEN"]\n'),
    ("env read in js", "const token = process.env.API_TOKEN;\n"),
    ("template", "API_TOKEN=${API_TOKEN}\n"),
    ("ci secret reference", "GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}\n"),
    ("placeholder value", "API_TOKEN=your-token-here-please-replace\n"),
    ("angle placeholder", "API_TOKEN=<paste-your-token-here-1234>\n"),
    ("short value", "PASSWORD_MIN_LENGTH=12\n"),
    ("path value", "GOOGLE_APPLICATION_CREDENTIALS=/run/secrets/key-2024.json\n"),
    ("url value", "TOKEN_ENDPOINT=https://auth.example.test/oauth2/token\n"),
    ("name-like value", "SECRET_NAME=projects/123456/secrets/db-password/versions/latest\n"),
    ("kebab identifier", "token_bucket: my-service-token-bucket-2\n"),
    ("key reference", "api_key_file: ./keys/dev-key-2.json\n"),
    ("header name", "AUTH_TOKEN_HEADER=X-Auth-Token-Value-1\n"),
    ("repeated characters", "TOKEN=aaaaaaaaaaaaaaaaaaaaaaaa1\n"),
    ("aws docs example", "AWS_ACCESS_KEY_ID=AKIAIOSFODNN7EXAMPLE\n"),
    ("pem header with no body", "const HEADER = '-----BEGIN PRIVATE KEY-----';\n"),
    ("public key", "-----BEGIN PUBLIC KEY-----\n" + PEM_BODY + "\n"),
    ("long minified line", "x=" + "a1" * 5000 + "\n"),
    ("git sha in a name", "release_sha: 0123456789abcdef0123456789abcdef01234567\n"),
    ("comment about tls", "# never set verify=False in production\n"),
    ("verify true", "requests.get(url, verify=True)\n"),
    ("unrelated VERIFY variable", "VERIFY=false ./deploy.sh\n"),
    ("compose without privilege", "services:\n  web:\n    image: nginx\n    privileged: false\n"),
    ("docker host env", "DOCKER_HOST: unix:///var/run/docker.sock\n"),
]

TLS_CONTENT = [
    "requests.get(url, verify=False)\n",
    "client = httpx.Client(verify=False)\n",
    "ctx = ssl._create_unverified_context()\n",
    "ctx.check_hostname = False\nctx.verify_mode = ssl.CERT_NONE\n",
    "const agent = new https.Agent({ rejectUnauthorized: false });\n",
    "process.env.NODE_TLS_REJECT_UNAUTHORIZED = '0';\n",
    "tls := &tls.Config{InsecureSkipVerify: true}\n",
    "curl_setopt($c, CURLOPT_SSL_VERIFYPEER, false);\n",
    "[http]\n\tsslVerify = false\n",
    "export GIT_SSL_NO_VERIFY=1\n",
    "clusters:\n- cluster:\n    insecure-skip-tls-verify: true\n",
]

DOCKER_CONTENT = [
    "services:\n  ci:\n    privileged: true\n",
    "services:\n  ci:\n    volumes:\n      - /var/run/docker.sock:/var/run/docker.sock\n",
    "services:\n  ci:\n    volumes:\n      - ${SOCK}:/var/run/docker.sock\n",
    '{"privileged": true}\n',
    "docker run --privileged -it alpine\n",
    "docker run \\\n  --privileged \\\n  img\n",
]


@pytest.mark.parametrize("label,text", SECRET_CONTENT, ids=[c[0] for c in SECRET_CONTENT])
def test_write_with_a_credential_is_blocked(rules_for, world, label, text):
    path = str(world["repo"] / "config.txt")
    assert "secret-in-content" in rules_for("Write", file_path=path, content=text)


@pytest.mark.parametrize("label,text", SAFE_CONTENT, ids=[c[0] for c in SAFE_CONTENT])
def test_write_of_ordinary_content_passes(rules_for, world, label, text):
    path = str(world["repo"] / "config.txt")
    assert rules_for("Write", file_path=path, content=text) == []


def test_edit_new_string_is_scanned_and_old_string_is_not(rules_for, world):
    path = str(world["repo"] / "app.py")
    bad = rules_for("Edit", file_path=path, old_string="x", new_string=f"T = '{GITHUB}'")
    assert bad == ["secret-in-content"]
    removing = rules_for("Edit", file_path=path, old_string=f"T = '{GITHUB}'", new_string="T = ''")
    assert removing == []


def test_multiedit_scans_every_edit(rules_for, world):
    path = str(world["repo"] / "app.py")
    edits = [
        {"old_string": "a", "new_string": "b"},
        {"old_string": "c", "new_string": f"T = '{GITHUB}'"},
    ]
    assert rules_for("MultiEdit", file_path=path, edits=edits) == ["secret-in-content"]


def test_notebook_edit_scans_new_source(rules_for, world):
    nb = str(world["repo"] / "n.ipynb")
    assert rules_for("NotebookEdit", notebook_path=nb, new_source=f"T='{GITHUB}'") == [
        "secret-in-content"
    ]
    assert rules_for("NotebookEdit", notebook_path=nb, edit_mode="delete") == []


@pytest.mark.parametrize(
    "name", [".env.example", ".env.sample", ".env.template", "example.env", "config.sample.yaml"]
)
def test_generic_assignments_are_allowed_in_placeholder_files(rules_for, world, name):
    path = str(world["repo"] / name)
    assert rules_for("Write", file_path=path, content=f"API_TOKEN={RANDOM_VALUE}\n") == []


def test_specific_token_formats_are_still_blocked_in_placeholder_files(rules_for, world):
    path = str(world["repo"] / ".env.example")
    assert rules_for("Write", file_path=path, content=f"TOKEN={GITHUB}\n") == ["secret-in-content"]


@pytest.mark.parametrize("text", TLS_CONTENT)
def test_tls_off_in_code_is_blocked(rules_for, world, text):
    path = str(world["repo"] / "client.cfg")
    assert "tls-verify-off" in rules_for("Write", file_path=path, content=text)


def test_tls_off_mentioned_in_docs_is_allowed(rules_for, world):
    path = str(world["repo"] / "docs.md")
    assert rules_for("Write", file_path=path, content="Never pass `verify=False`.\n") == []


@pytest.mark.parametrize("text", DOCKER_CONTENT)
def test_privileged_container_in_files_is_blocked(rules_for, world, text):
    path = str(world["repo"] / "compose.yaml")
    assert "docker-privileged" in rules_for("Write", file_path=path, content=text)


def test_secret_in_docs_is_still_blocked(rules_for, world):
    path = str(world["repo"] / "README.md")
    assert "secret-in-content" in rules_for("Write", file_path=path, content=f"key {GITHUB}\n")


@pytest.mark.parametrize(
    "tool,field",
    [("Write", "content"), ("Edit", "new_string")],
)
def test_missing_content_cannot_be_judged(rules_for, world, tool, field):
    path = str(world["repo"] / "a.txt")
    assert rules_for(tool, file_path=path) == ["cannot-decide"]
    assert rules_for(tool, file_path=path, **{field: 12}) == ["cannot-decide"]


def test_missing_path_cannot_be_judged(rules_for):
    assert rules_for("Write", content="x") == ["cannot-decide"]


# --- Read and Grep ------------------------------------------------------------------


@pytest.mark.parametrize(
    "name",
    [".env", ".env.local", "deploy.pem", "id_rsa", "id_ed25519", "prod.key", "app.p12",
     "service-account.json", "application_default_credentials.json", ".netrc", ".pgpass"],
)  # fmt: skip
def test_reading_a_secret_file_is_blocked(rules_for, world, name):
    path = str(world["repo"] / name)
    assert rules_for("Read", file_path=path) == ["secret-file-read"]
    assert rules_for("Grep", pattern="x", path=path) == ["secret-file-read"]


@pytest.mark.parametrize(
    "rel",
    [".aws/credentials", ".config/gcloud/application_default_credentials.json",
     ".config/gcloud/legacy_credentials/me/adc.json", ".ssh/deploy_key", ".config/gh/hosts.yml",
     ".docker/config.json", ".kube/config", ".npmrc"],
)  # fmt: skip
def test_reading_home_level_credentials_is_blocked(rules_for, world, rel):
    path = str(world["home"] / rel)
    assert rules_for("Read", file_path=path) == ["secret-file-read"]


@pytest.mark.parametrize(
    "name",
    [".env.example", ".env.sample", "id_rsa.pub", "server.crt", "environment.py", ".envrc",
     "README.md", "settings.json", "pem-guide.md", "keys.txt", "config.json"],
)  # fmt: skip
def test_reading_ordinary_files_is_allowed(rules_for, world, name):
    path = str(world["repo"] / name)
    assert rules_for("Read", file_path=path) == []


def test_reading_a_project_npmrc_and_known_hosts_is_allowed(rules_for, world):
    assert rules_for("Read", file_path=str(world["repo"] / ".npmrc")) == []
    assert rules_for("Read", file_path=str(world["home"] / ".ssh" / "known_hosts")) == []
    assert rules_for("Read", file_path=str(world["home"] / ".ssh" / "config")) == []


def test_a_symlink_to_a_secret_file_is_still_that_file(rules_for, world):
    secret = world["repo"] / ".env"
    link = world["repo"] / "notes.txt"
    link.symlink_to(secret)
    assert rules_for("Read", file_path=str(link)) == ["secret-file-read"]


def test_grep_over_a_directory_is_not_blocked(rules_for, world):
    # documented limit: only a Grep path that names a secret file is judged
    assert rules_for("Grep", pattern="x", path=str(world["repo"])) == []
    assert rules_for("Grep", pattern="x") == []


# --- guardrails' own files ----------------------------------------------------------


def test_writing_the_allowlist_is_tamper(rules_for, world):
    path = str(world["repo"] / ".claude" / "guardrails-allow.txt")
    assert "guardrails-tamper" in rules_for("Write", file_path=path, content="git-push-protected\n")
    assert "guardrails-tamper" in rules_for("Edit", file_path=path, old_string="a", new_string="b")
    other = str(world["home"] / "elsewhere" / "guardrails-allow.txt")
    assert "guardrails-tamper" in rules_for("Write", file_path=other, content="x\n")


def test_writing_plugin_files_or_the_log_is_tamper(rules_for, world):
    plugin_file = world["env"]["CLAUDE_PLUGIN_ROOT"] + "/hooks/guardrails.py"
    assert "guardrails-tamper" in rules_for(
        "Edit", file_path=plugin_file, old_string="a", new_string="b"
    )
    log = str(world["data"] / "blocks.log")
    assert "guardrails-tamper" in rules_for("Write", file_path=log, content="")


@pytest.mark.parametrize(
    "content",
    ['{"disableAllHooks": true}', '{"enabledPlugins": {"guardrails@claude-pack": false}}'],
)
def test_settings_that_switch_hooks_off_are_tamper(rules_for, world, content):
    path = str(world["repo"] / ".claude" / "settings.local.json")
    assert "guardrails-tamper" in rules_for("Write", file_path=path, content=content)


def test_ordinary_settings_are_fine(rules_for, world):
    path = str(world["repo"] / ".claude" / "settings.json")
    content = '{"permissions": {"allow": ["Bash(git status)"]}}'
    assert rules_for("Write", file_path=path, content=content) == []


def test_reading_the_allowlist_is_fine(rules_for, world):
    path = str(world["repo"] / ".claude" / "guardrails-allow.txt")
    assert rules_for("Read", file_path=path) == []


def test_other_tools_are_ignored(rules_for):
    assert rules_for("WebFetch", url="https://example.test") == []
    assert rules_for("Glob", pattern="**/*.pem") == []
