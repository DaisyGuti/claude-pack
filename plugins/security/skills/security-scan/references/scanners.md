# How the scanners are run and merged

Contents:
- Scanner table
- Severity mapping
- De-duplication rules
- Suppression files
- What the report never contains
- Sources

## Scanner table

| Tool | Finds | Command the script runs | Exit codes accepted | Network use |
| --- | --- | --- | --- | --- |
| gitleaks | committed secrets, in the working tree and in git history | `gitleaks dir <repo>` and, when `.git` exists, `gitleaks git <repo>`, both with `--redact --report-format json --exit-code 0` | 0 | none |
| osv-scanner (v2) | vulnerable dependencies from lockfiles and manifests | `osv-scanner scan source -r --format json --output-file <raw> <repo>` | 0 (clean), 1 (vulnerabilities found); 128 means no supported files, reported as `no input` | queries OSV and deps.dev |
| grype | vulnerable dependencies | `grype dir:<repo> -o json -q` | 0 | downloads its database on first use |
| semgrep | code flaws (SAST) | `semgrep scan --json --quiet --metrics off --disable-version-check --config <cfg> <repo>` | 0 | fetches registry rules unless `--semgrep-config` points at local rules |
| trivy | vulnerable dependencies and IaC misconfigurations | `trivy fs --format json --scanners vuln,misconfig --quiet --output <raw> <repo>` | 0 | downloads its databases on first use |
| checkov | IaC misconfigurations (Terraform, CloudFormation, Kubernetes, Dockerfile and others) | `checkov -d <repo> -o json --quiet` | 0 (clean), 1 (failed checks) | none for the scan itself |

Any other exit code marks the tool `failed` and the last 500 characters of its output go in the
Coverage table. A tool that runs past `--timeout` (600 seconds by default) is stopped and marked
`failed`. The other tools still run.

Two tools can report the same dependency problem. That is intended: a second source catches what
the first misses, and the merge step collapses the overlap.

trivy's secret scanner is switched off (`--scanners vuln,misconfig`) because gitleaks owns the
secrets role. Each tool's own version-check or telemetry options stay at the tool default except
for semgrep, where metrics are off.

## Severity mapping

Every finding ends up as `critical`, `high`, `medium`, `low`, `info` or `unknown`.

| Source | Rule |
| --- | --- |
| osv-scanner | the group's `max_severity` is a CVSS base score; it maps to the qualitative bands of the CVSS specification (9.0 and above critical, 7.0 to 8.9 high, 4.0 to 6.9 medium, 0.1 to 3.9 low). With no score, the advisory's own severity label is used. |
| grype, trivy | the tool's severity word. grype's "Negligible" becomes `info`. |
| semgrep | ERROR is high, WARNING is medium, INFO is low. |
| gitleaks | high for every secret. gitleaks has no severity, and a committed credential is usable by anyone who can read the repository. |
| checkov | the tool's severity when present. Without a paid account checkov gives none, so the finding is `medium` and its note says the severity was assumed. |

When two tools disagree about one finding, the worse severity is kept.

## De-duplication rules

- **Dependencies** merge when the package name (case-insensitive), the installed version and at
  least one vulnerability ID match. The IDs come from every alias the tools report (CVE, GHSA,
  PYSEC), so a grype GHSA entry and an osv-scanner CVE entry for the same flaw become one.
- **Secrets** merge when file and line match, which joins the working-tree pass and the history
  pass of gitleaks.
- **Code and IaC findings** merge when kind, file, line and rule match.
- The merged finding lists every tool that reported it under `Found by`.

One overlap the merge cannot resolve: trivy and checkov both report infrastructure-as-code
problems, and their rule IDs differ. The same misconfiguration can therefore appear twice, once
from each tool. Treat the two entries as one when file and line match.

Findings are numbered `SS-001` onward in report order: severity first, then secrets, code, IaC
and dependencies within a severity, then file and line.

## Suppression files

The scanners read ignore and allowlist files from the repository (`.gitleaks.toml`,
`.gitleaksignore`, `.semgrepignore`, `.trivyignore`, `.trivyignore.yaml`, `.grype.yaml`,
`osv-scanner.toml`, `.checkov.yaml`, `.checkov.yml`) and leave out the findings they match. The
report lists each one it finds so a reviewer can read what is being hidden.

## What the report never contains

- Secret values. The gitleaks parser reads the rule, file, line and commit only, and gitleaks
  runs with `--redact` as well.
- Matched source lines from semgrep. The parser does not copy them.

The raw tool output kept under `<out>/raw/` is not filtered. It can hold matched lines when
semgrep is logged in to the Semgrep platform.

## Sources

- gitleaks: https://github.com/gitleaks/gitleaks
- osv-scanner: https://google.github.io/osv-scanner/
- grype: https://github.com/anchore/grype
- semgrep CLI reference: https://docs.semgrep.dev/cli-reference and metrics:
  https://docs.semgrep.dev/metrics
- trivy: https://trivy.dev/latest/docs/ (reporting schema:
  https://trivy.dev/latest/docs/configuration/reporting/)
- checkov: https://www.checkov.io/2.Basics/CLI%20Command%20Reference.html
- CVSS qualitative severity rating scale: https://www.first.org/cvss/v4-0/specification-document

The JSON shapes the parsers read were captured from live runs of gitleaks 8.30, osv-scanner 2.3,
semgrep, checkov 3.3, trivy 0.76 and grype 0.120.
