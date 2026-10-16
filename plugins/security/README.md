# security

Security and compliance work on source code and system design for a government product.

| Piece | What it does |
| --- | --- |
| `threat-model` skill | STRIDE threat model of a design, feature or repository: Mermaid data flow diagram, trust boundaries, assets, abuse cases, ranked threats, and mitigations mapped to NIST SP 800-53 Rev 5 controls, written to a document the team reviews |
| `security-scan` skill | Runs the free scanners that are installed (gitleaks, osv-scanner, grype, semgrep, trivy, checkov) and merges their output into one de-duplicated findings report with severity, `file:line` and a fix |
| `compliance-map` skill | Maps repository evidence to NIST SP 800-53 Rev 5 with FedRAMP, NIST SSDF, NIST SP 800-171 and CMMC, the DoD Cloud Computing SRG, FIPS 140-3 and SBOM expectations. Lists evidence and gaps only and never says a system is compliant or authorized |
| `security-auditor` agent | Read-only auditor. Runs the scanners, reviews the code for government control gaps, challenges every finding, and returns a ranked list |

## Install these official plugins too

This plugin builds only what they leave open.

```sh
/plugin install claude-security@claude-plugins-official
/plugin install security-guidance@claude-plugins-official
```

- `claude-security` scans a codebase or a diff with agents, verifies every finding before it
  reports it, and can write patch files. Use it for deep vulnerability hunting.
- `security-guidance` warns while code is edited, reviews the diff when a turn ends, and reviews
  each commit. Use it for continuous guidance.

Use `security-scan` for fast, wide coverage from the standard open-source tools, then
`claude-security` for depth. Use `threat-model` before building and `compliance-map` when a
customer asks for evidence.

## Where other work lives

- Hardened Dockerfiles and images, image scanning and signing, SBOM generation, pipeline
  hardening and GitHub-to-GitLab migration: the `secure-build` plugin.
- Hooks that block risky commands and secret leaks as Claude works: the `guardrails` plugin.
- A separate secure code review skill was considered and left out. The official plugins find the
  vulnerabilities, and the government-specific checks (validated cryptography, audit logging,
  identity and session handling, access control) are in the `security-auditor` agent and, as
  per-control evidence, in `compliance-map`.

## Requirements

- Python 3.11 or later for the scripts. They use only the standard library.
- Any of the scanners above. `security-scan` lists which are installed and prints an install
  command for each missing one. It never installs anything on its own.
- Network access to fetch the NIST catalog, the FedRAMP rules and the other sources that
  `compliance-map` reads at run time.

## Scripts

| Script | Used by | Purpose |
| --- | --- | --- |
| `skills/security-scan/scripts/security_scan.py` | `security-scan` | detect, run and merge scanners |
| `scripts/nist_catalog.py` | `threat-model`, `compliance-map` | fetch and query the NIST SP 800-53 Rev 5 catalog and baselines |
| `scripts/security_doc_check.py` | `threat-model`, `compliance-map` | check control IDs and the structure of the documents these skills write |

Tests are in `tests/security/` at the repository root and run with `uv run pytest tests/security`.
