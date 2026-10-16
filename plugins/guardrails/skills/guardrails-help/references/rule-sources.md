# Rule sources

Facts the rules rely on, with where each came from. Fetched 2026-10-16. Re-check a row before
changing the rule behind it.

## Contents

- Hook behavior
- Credential formats
- GCP
- Gaps

## Hook behavior

| Fact | Source |
| --- | --- |
| A PreToolUse command hook that exits 2 blocks the call and its stderr reaches Claude | https://code.claude.com/docs/en/hooks |
| A timeout or a failed start does not block unless `onFailure: "block"` is set (Claude Code 2.1.295 or later) | https://code.claude.com/docs/en/hooks |
| Exec form (`command` plus `args`) spawns without a shell and substitutes `${CLAUDE_PLUGIN_ROOT}` into each argument | https://code.claude.com/docs/en/hooks |
| `CLAUDE_PROJECT_DIR`, `CLAUDE_PLUGIN_ROOT` and `CLAUDE_PLUGIN_DATA` are exported to the hook process. Confirmed on a live run: the block log landed in the plugin data directory | https://code.claude.com/docs/en/hooks |
| `tool_input` fields: Bash `command`; Write `file_path`, `content`; Edit `file_path`, `old_string`, `new_string`; Read `file_path`; Grep `pattern`, `path`, `glob`. File paths arrive absolute with `~` expanded | https://code.claude.com/docs/en/hooks#pretooluse-input |
| `!` shell mode runs a command "without going through Claude", and PreToolUse "runs only when Claude calls a tool" | https://code.claude.com/docs/en/interactive-mode and the hooks page |
| `@file` references insert contents without a tool call, so no Read hook fires; `CLAUDE_CODE_DISABLE_FILE_MENTIONS=1` (2.1.299 or later) routes them through Read | https://code.claude.com/docs/en/hooks |
| A PowerShell tool exists on Windows; matchers for shell commands should include it there | https://code.claude.com/docs/en/hooks |

## Credential formats

| Format | Source |
| --- | --- |
| GitHub `ghp_`, `gho_`, `ghu_`, `ghs_`, `ghr_`, `github_pat_` | https://docs.github.com/en/authentication/keeping-your-account-and-data-secure/about-authentication-to-github |
| GitLab `glpat-`, `gloas-`, `gldt-`, `glrt-`, `glrtr-`, `glcbt-`, `glptt-`, `glft-`, `glimt-`, `glagent-`, `glsoat-`, `glffct-` | https://docs.gitlab.com/security/tokens/ |
| AWS access key ID prefixes `AKIA` (long-term) and `ASIA` (temporary) | https://docs.aws.amazon.com/IAM/latest/UserGuide/reference_identifiers.html |
| Slack `xoxb-`, `xoxp-`, `xapp-` (also `xoxe.xapp-`) | https://docs.slack.dev/authentication/tokens |
| Slack `xoxa-`, `xoxr-`, `xoxs-`, `xoxo-`, `xoxe-` and webhook URLs under `hooks.slack.com/services/` | Common scanner patterns; the Slack page above omits them (UNVERIFIED against Slack docs) |
| Google API keys start `AIza`; OAuth client secrets start `GOCSPX-` | Common scanner patterns (UNVERIFIED against Google docs) |
| Anthropic API keys start `sk-ant-` | Common scanner patterns (UNVERIFIED against Anthropic docs) |
| A service account key file is JSON with `"type": "service_account"`, `private_key_id` and `private_key` | https://docs.cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys (key alternatives and risk) |

The content check also matches the PEM private-key header followed by key material, and
`NAME=value` assignments whose name contains SECRET, TOKEN, PASSWORD, API_KEY and similar words,
when the value is long, mixes letters and digits, has high entropy, and is not a placeholder,
path, URL or variable reference. That heuristic is a judgment call with no published standard behind it.

## GCP

| Fact | Source |
| --- | --- |
| `allUsers` is "anyone who is on the internet, including authenticated and unauthenticated users"; `allAuthenticatedUsers` is all users and service accounts authenticated with a Google Account | https://docs.cloud.google.com/iam/docs/principals-overview |
| Google recommends managed workload identities, Workload Identity Federation, attached service accounts and OAuth user credentials over service account keys | https://docs.cloud.google.com/iam/docs/best-practices-for-managing-service-account-keys |
| `gsutil iam ch -d` removes a binding, so it passes; `gcloud ... remove-iam-policy-binding` passes | `gsutil help iam ch` text (UNVERIFIED here: gsutil was not installed when the rule was written) |
| `gcloud run deploy ... --allow-unauthenticated` is the documented way to "make your service publicly accessible". The rule matches that exact flag, so `--no-allow-unauthenticated` passes (that spelling was not on the page fetched; UNVERIFIED) | https://docs.cloud.google.com/run/docs/authenticating/public |

## Gaps

- `git` hooks are skipped by `HUSKY=0` only when it is set on the same command as the commit or
  push. A separate `export HUSKY=0` earlier in a session is not tracked.
- `gsutil` is the legacy tool. The rules read both it and `gcloud storage`.
