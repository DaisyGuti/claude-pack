---
name: section-508-report
description: >-
  Builds an Accessibility Conformance Report (ACR) on the ITI VPAT 2.5Rev template from audit
  findings and test notes - the WCAG Level A and AA rows plus Revised Section 508 chapters 3, 5
  and 6, each marked Supports, Partially Supports, Does Not Support, Not Applicable or Not
  Evaluated with remarks, plus the GSA ACR Issue Detail Supplement. Use when asked to fill in a
  VPAT, write an ACR or Section 508 conformance report, answer a federal buyer's accessibility
  questionnaire, or turn accessibility audit results into a customer-facing statement, even if
  the user does not say VPAT. Refuses to mark a row Supports without a passing check run by a
  person, lists the rows that still need a human tester (keyboard, screen reader), and never
  declares a product compliant. It does not run the audit itself; use the AccessLint skills for
  scanning, inspecting, auditing or fixing. For FedRAMP, NIST 800-53, CMMC or SSDF evidence, use
  compliance-map (security plugin).
argument-hint: "[path to audit report or evidence file]"
allowed-tools: Read Write Bash(${CLAUDE_SKILL_DIR}/scripts/acr.py *) WebFetch(domain:www.itic.org) WebFetch(domain:www.section508.gov)
---

# Section 508 report (ACR on the VPAT)

An ACR is a vendor's statement to buyers about how a product meets the Revised Section 508
standards. A wrong "Supports" in one misleads a buyer and exposes the company, so this skill
is built around one rule: **no answer goes in the report that the evidence does not carry.**

- A row is Supports only when a person has run a check on it and it passed. A rule-engine
  scan or an assistant reading code does not count as that check.
- A row nobody tested stays Not Evaluated, and the report stays a draft until it is tested.
- The skill states evidence and gaps. It never writes that the product "is compliant" or "meets
  Section 508". The people who sign for the company decide that.

`${CLAUDE_SKILL_DIR}/scripts/acr.py` enforces the rules. Read
`${CLAUDE_SKILL_DIR}/references/evidence-rules.md` for the evidence file and
`${CLAUDE_SKILL_DIR}/references/vpat-structure.md` for the template. Do not write the report by
hand.

## Steps

1. **Collect the facts only the team has.** Company name as it should print, product name and
   version, report date, contact email, a one-line product description, who ran each test and
   with what assistive technology, and which WCAG version the contract or buyer names. Ask for
   what is missing, in one message. Without a stated requirement, use `2.0`, which is what
   Section 508 incorporates.
2. **Check the current template.** Fetch `https://www.itic.org/policy/accessibility/vpat`,
   read the current version and the edition download links, download the edition for the
   chosen version with `curl -sSL -o <tmp>/vpat.docx <link>` (Revised Section 508 for `2.0`,
   International for `2.1` or `2.2`), then run
   `${CLAUDE_SKILL_DIR}/scripts/acr.py check-template <tmp>/vpat.docx`. Exit 1 means rows or the
   version moved. Stop, tell the user what differs, and do not render. Delete the download
   afterwards.
3. **Start the evidence file** in the project's docs folder (not inside the plugin):

   ```sh
   ${CLAUDE_SKILL_DIR}/scripts/acr.py init --wcag 2.0 --web-only --out acr-evidence.json
   ```

   `--web-only` pre-fills sections 502, 503 and 504 as Not Applicable (the VPAT instructions
   say 502 and 503 do not apply to a web-only application) and flags them for the team to
   confirm.
4. **Fill it from the findings.** Register each test run as a session, then give each row a
   status, remarks and evidence. Map an AccessLint audit, a scan export or the team's own notes
   with the table in `${CLAUDE_SKILL_DIR}/references/evidence-rules.md`. Write remarks that name the feature and the
   effect. Copy no tester, date or result that the sources do not contain.
5. **Validate and repair.**

   ```sh
   ${CLAUDE_SKILL_DIR}/scripts/acr.py validate acr-evidence.json
   ```

   Fix every error. Each message names the row and what to add. Lower the status instead of
   inventing evidence.
6. **List the human work.**

   ```sh
   ${CLAUDE_SKILL_DIR}/scripts/acr.py needs-human acr-evidence.json
   ```

   Give the user this list grouped by check kind (keyboard, screen reader, visual, media,
   pointer, content, documentation) with the flows to cover. It is the plan for the testers.
7. **Render.** Markdown for review, HTML for publishing:

   ```sh
   ${CLAUDE_SKILL_DIR}/scripts/acr.py render acr-evidence.json --format md --out acr.md
   ${CLAUDE_SKILL_DIR}/scripts/acr.py render acr-evidence.json --format html --out acr.html --final
   ```

   Without `--final` the output carries a DRAFT banner and an "Open items" section whenever
   anything is unresolved. `--final` refuses to render while open items remain. The VPAT requires
   the published report to be accessible, so scan the HTML (`accesslint:accessibility-scan` if it
   is installed) and fix what it finds before the report leaves the company.
8. **Supplement.** When the report has known issues and a buyer may ask for GSA's ACR Issue
   Detail Supplement, fill `issues` in the evidence file. The report then includes the section,
   and `acr.py supplement acr-evidence.json --out issues.csv` writes the same rows as CSV.
9. **Report to the user** in plain words: how many rows are evidenced, which are open and what
   check each needs, the draft or final state, the template version used, and what the user has
   to decide (publish, who signs, whether to test the open rows first).

## Limits

- Web products only. A product with hardware (Chapter 4) or non-web software (where 502 and 503
  apply) needs the VPAT filled in directly.
- One report per product. For a product with several parts (a web app and an authoring tool,
  say), write one report each and cross-reference them in the Notes, which the VPAT permits.
- The skill does not run tests. Scanning, keyboard and screen-reader inspection, and whole-site
  audits belong to the AccessLint skills (`accesslint:accessibility-scan`, `-inspect`, `-audit`),
  which the `accessibility` plugin's README recommends installing.
- USWDS test results for its own components are context for a row and never replace testing the
  product.
