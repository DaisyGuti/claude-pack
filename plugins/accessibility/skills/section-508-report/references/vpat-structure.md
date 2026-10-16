# The VPAT template and what federal buyers expect

What the ITI VPAT 2.5Rev template requires, as read from its three Word editions, and what
GSA's Section508.gov guidance adds. The bundled row data and report layout follow this page.
The edition and the rows are re-checked every run (see "Checking the current edition").

## Contents

- [Editions and which one to use](#editions-and-which-one-to-use)
- [What every report must contain](#what-every-report-must-contain)
- [Answers and their definitions](#answers-and-their-definitions)
- [Rows this skill answers and rows the template answers](#rows-this-skill-answers-and-rows-the-template-answers)
- [Sections that may be removed](#sections-that-may-be-removed)
- [What federal buyers ask for](#what-federal-buyers-ask-for)
- [Checking the current edition](#checking-the-current-edition)
- [Sources](#sources)

## Editions and which one to use

The ITI landing page lists four editions of the current version: Revised Section 508, WCAG,
EN 301 549 and International. The Word files read for this skill are version 2.5Rev.

| Edition | Standards it covers | Used here |
|---|---|---|
| Revised Section 508 | WCAG 2.0 and the Revised Section 508 standards | `wcag_version: "2.0"` |
| WCAG | WCAG 2.0, 2.1 and 2.2 | not used (no Section 508 chapters) |
| International | WCAG 2.0, 2.1, 2.2, Revised Section 508 and EN 301 549 | `wcag_version` 2.1 or 2.2, with EN 301 549 answered "No" |

Section 508 incorporates WCAG 2.0 Level A and AA. The Revised 508 edition therefore holds only
WCAG 2.0 criteria. A buyer who also asks for WCAG 2.1 or 2.2 needs the International layout,
where each added criterion is marked "2.1 and 2.2" or "2.2 only" and, for Section 508, does not
apply. Ask the user which one the contract or the buyer names, and say which was used.

## What every report must contain

From the template's "Essential Requirements for Authors". A report deviating from them cannot
use the VPAT name.

1. Report title in the form "[Company Name] Accessibility Conformance Report".
2. The template version ("Based on VPAT® Version 2.5Rev"), with the registered service mark.
3. Name of product and version.
4. Report date (at least month and year).
5. A brief product description.
6. Contact information for questions.
7. Notes (may be blank).
8. Evaluation methods used.
9. Applicable standards and guidelines, with only the ones actually used.
10. The definitions of the terms used in the Conformance Level column.
11. A table for each standard, with a response and remarks for each criterion.

The final report must itself be accessible, and the instruction pages of the template are
removed before publishing. `acr.py render --format html` produces a semantic document (language,
title, table captions and header cells). Scan the result before it goes out.

## Answers and their definitions

| Answer | Template definition |
|---|---|
| Supports | The functionality of the product has at least one method that meets the criterion without known defects or meets with equivalent facilitation. |
| Partially Supports | Some functionality of the product does not meet the criterion. |
| Does Not Support | The majority of product functionality does not meet the criterion. |
| Not Applicable | The criterion is not relevant to the product. |
| Not Evaluated | The product has not been evaluated against the criterion. This can only be used in WCAG Level AAA criteria. |

More rules from the template:

- Remarks are required for Partially Supports and Does Not Support, and must identify the
  functions or features with issues and how they do not fully support the criterion. For Not
  Applicable they explain why. If an accessible alternative exists, describe it.
- When filling the WCAG tables, Supports may be used where Not Applicable might otherwise be
  chosen. WCAG 2.0 "Understanding Conformance" says that if there is no content to which a
  criterion applies, the criterion is satisfied.
- All Level A and Level AA criteria must be answered. A Level AAA table may be deleted when AAA
  is not evaluated. Section508.gov says Section 508 does not require AAA.

## Rows this skill answers and rows the template answers

- **WCAG 4.1.1 Parsing.** The template answers Supports for WCAG 2.0 and 2.1, citing the
  September 2023 errata, and marks the criterion obsolete and removed in WCAG 2.2.
  `acr.py` fills this row itself.
- **Cross-reference rows** 501.1, 504.2 and 602.3 read "See WCAG 2.x section". `acr.py` fills them.
- **Heading rows** in the Section 508 tables take no response.
- **Chapter 3** (302.1 to 302.9), **Chapter 5** (502.x, 503.x, 504.x rows) and **Chapter 6**
  (602.2, 602.4, 603.2, 603.3) are answered row by row.
- Chapter 3's scope comes from E204.1 of the Revised 508 Standards: it applies to functions that
  Chapters 4 and 5 do not address. Section508.gov tells sellers to complete it when the product
  has functions the technical chapters do not cover.

## Sections that may be removed

The template says an entire section that does not apply may be removed when the notes explain
why, and that individual criteria may not be removed. Two uses here:

- **Chapter 4 (Hardware)** is replaced by a note that the product is delivered over the web and
  has no hardware component. If the product has hardware, fill the template in directly.
- **Sections 502 and 503** do not apply to a web-only application, in the template's own words.
  `acr.py init --web-only` pre-fills those rows (and 504, "not an authoring tool") as Not
  Applicable and flags them for the team to confirm. The rows stay in the report with a reason.

## What federal buyers ask for

From Section508.gov, "How to create an ACR with a VPAT" (reviewed June 2026):

- A seller to the federal government uses the Revised Section 508 edition or the International
  edition. Any VPAT 2.x is acceptable.
- Complete all of the header fields, the Level A and AA tables, the Chapter 3 table where the
  product has functions the technical chapters do not address, and the chapters that apply.
- Use only the four answer phrases for Level A and AA, and fill remarks for partial and negative
  answers.
- Check the final document for accessibility.

Section508.gov also publishes the **ACR Issue Detail Supplement** (reviewed October 2026),
which buyers may require alongside the ACR. It asks, for each known issue, for a severity
(critical, major or minor), the area impacted and how extensive it is, the impacted user group
and the workaround. `acr.py` carries these in the `issues` list.

The Access Board's ICT Testing Baseline (`https://ictbaseline.access-board.gov/`) is the
published test procedure for Section 508 conformance of web content. A session that follows it
is recorded with `method: published-procedure` and the baseline named in `scope`.

## Checking the current edition

The bundled rows were read from version 2.5Rev. Every run, fetch
`https://www.itic.org/policy/accessibility/vpat`, read the current version and the download
links, download the edition for the chosen `wcag_version` (Revised Section 508 for 2.0,
International for 2.1 or 2.2) and run the skill's `scripts/acr.py` (SKILL.md has the full path):

```sh
acr.py check-template <downloaded edition>.docx
```

It compares the version and the row ids with the bundled data and exits 1 on any difference.
On a difference, stop, tell the user which rows or version moved, and do not render until the
bundled data is updated. Row titles and the template's wording (terms, notes) live in
`data/criteria.json` and `data/vpat-text.json`; `check-template` checks ids and version only,
so also skim the downloaded file's terms and instructions for changes.

## Sources

Read on 2026-10-16:

- ITI VPAT landing page and the Revised Section 508, WCAG and International edition Word files,
  version 2.5Rev, released April 2025: https://www.itic.org/policy/accessibility/vpat
- Section508.gov, how to create an ACR with a VPAT: https://www.section508.gov/sell/how-to-create-acr-with-vpat/
- Section508.gov, ACR Issue Detail Supplement: https://www.section508.gov/sell/acr-supplement/
- Revised 508 Standards (E204.1, E205.4, E207.2, Chapters 3, 5, 6): https://www.access-board.gov/ict/
- ICT Testing Baseline: https://ictbaseline.access-board.gov/
