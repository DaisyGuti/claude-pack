# accessibility

Section 508 reporting for a government web product. The WCAG scan, inspect, audit, fix and diff
skills come from AccessLint, which publishes its own Claude Code marketplace, so they are
installed from there and are not copied into this plugin.

| Piece | What it does |
|---|---|
| `section-508-report` | Builds an Accessibility Conformance Report on the ITI VPAT 2.5Rev template from audit findings and test notes: the WCAG A and AA rows plus Section 508 chapters 3, 5 and 6, with remarks and an issue list in the form GSA's supplement asks for. It refuses to mark a row Supports without a passing check run by a person, and lists which rows still need a tester. |

## Install the WCAG tooling alongside

```sh
claude plugin marketplace add accesslint/skills
claude plugin install accesslint@accesslint
```

That adds `accesslint:accessibility-scan`, `-inspect`, `-audit`, `-fix` and `-diff` (MIT) and
their MCP server. Read before installing on a work machine: the skills and the bundled MCP server
run `npx -y @accesslint/...@latest` (Chrome launcher, CLI and server) when they run, so each run
fetches whatever npm currently serves for those packages.

## How the two fit

1. Run `accesslint:accessibility-audit` on the product (or collect the team's own test notes).
2. Have people run the keyboard and screen-reader checks the audit hands off.
3. Ask for an ACR. `section-508-report` turns the findings and the sessions into the report and
   marks what is still open.
