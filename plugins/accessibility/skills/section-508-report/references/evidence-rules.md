# The evidence file and the rules for each answer

`scripts/acr.py` works from one JSON evidence file. This page says what goes in it and what
each answer must be backed by. The script enforces these rules; the reasons are here so that
the person filling the file knows what to fix.

## Contents

- [File layout](#file-layout)
- [Sessions: who ran each check](#sessions-who-ran-each-check)
- [What each answer needs](#what-each-answer-needs)
- [Turning audit output into rows](#turning-audit-output-into-rows)
- [The issue list for the GSA supplement](#the-issue-list-for-the-gsa-supplement)
- [Check kinds a person runs](#check-kinds-a-person-runs)
- [What the script cannot decide](#what-the-script-cannot-decide)

## File layout

`acr.py init` writes a starter file. A filled-in one looks like
`templates/evidence.example.json`. Top level:

| Key | Holds |
|---|---|
| `report` | The header the VPAT requires: `company`, `product` (with version), `report_date`, `description`, `contact`, `evaluation_methods` (prose), `vpat_version`, plus optional `notes` and `legal_disclaimer`. `product_has_hardware` must stay false. |
| `wcag_version` | `"2.0"` for the Revised Section 508 edition (Section 508 incorporates WCAG 2.0). `"2.1"` or `"2.2"` adds the criteria those versions introduced and switches to the International edition layout with EN 301 549 marked not covered. |
| `sessions` | Every test session that backs an answer. |
| `rows` | One entry per answerable criterion, keyed by id: `status`, `remarks`, `evidence`. |
| `issues` | Optional. The known issues for the GSA supplement. |

A row with no entry reads Not Evaluated. Heading rows, the cross-reference rows (501.1,
504.2, 602.3) and WCAG 4.1.1 are answered by the template and have no entry. Chapter 4
(Hardware) is left out with a stated reason, because this skill reports web products.

## Sessions: who ran each check

A session is one test run, recorded once and referenced by many rows.

| Field | Rule |
|---|---|
| `id` | Unique. |
| `method` | One of `automated`, `code-review`, `keyboard`, `screen-reader`, `visual`, `media`, `pointer`, `content`, `documentation`, `platform`, `published-procedure`. Use `published-procedure` for a named method such as the Section 508 ICT Testing Baseline or DHS Trusted Tester, and say which in `scope`. |
| `by` | `human` (a person ran it), `tool` (a rule engine or scanner ran it) or `assistant` (an AI assistant read code or ran commands). |
| `tester` | Required when `by` is `human`: the role and the assistive technology used ("QA engineer, NVDA with Firefox"). It appears in the published report, so write what the team is willing to publish. |
| `tool` | Required when `by` is `tool`. |
| `date`, `scope`, `ref` | When it ran, what it covered, and where the raw results live. |

The distinction matters because a rule engine finds only part of the real defects, and an
assistant reading markup is not a tester. OMB M-23-22 says the same about agencies: automated
tools "can only detect some accessibility issues", so manual testing is needed. A person's
session is the only thing that can back a Supports answer.

## What each answer needs

| Answer | The evidence file must show |
|---|---|
| Supports | At least one `pass` result from a session run by a person, and no `fail` result on the row. VPAT definition: at least one method meets the criterion without known defects. |
| Partially Supports | At least one `fail` result, and remarks that name the functions or features with issues and how they fail. VPAT definition: some functionality does not meet the criterion. |
| Does Not Support | At least one `fail` result and remarks as above. VPAT definition: the majority of functionality does not meet the criterion. The status is the author's judgment of the extent; the script checks that a failure is recorded. |
| Not Applicable | Remarks that say why. On a WCAG row the VPAT note says Supports fits when no content exists to which the criterion applies, so the script warns. Use Not Applicable on WCAG rows only when Supports would mislead. |
| Not Evaluated | Nothing. The VPAT allows this answer only for Level AAA, so on any other row it keeps the report a draft and the row goes to the open items. |

`evidence` entries look like `{"session": "kbd-1", "result": "pass", "detail": "Apply and pay
flows completed without a mouse"}`. `result` is `pass`, `fail` or `n/a`. `detail` is free
text that should let a reader find the proof.

A `Supports` row with remarks is better than one without. The VPAT encourages remarks and
requires them only for the partial and negative answers.

## Turning audit output into rows

For an AccessLint audit report (`accesslint:accessibility-audit`), or any report that grades
each criterion:

| In the audit | In the evidence file |
|---|---|
| Fail with evidence basis "verified" | A `fail` result from a `tool` or `human` session, and a Partially Supports or Does Not Support row with remarks written from the finding (the selector, page and effect). |
| Pass with evidence basis "verified" | A `pass` result. By itself it cannot make the row Supports, because no person has run a check. |
| Flagged, human-required or undetermined | No result. The row stays Not Evaluated and goes to the person who runs the check. |
| Not applicable | Not Applicable with the reason, or Supports on a WCAG row when no content exists, backed by a person's review. |

Record the audit as a `tool` session (and the keyboard or screen-reader pass it prepared as
`human` sessions only once a person has actually run them). Never create a `human` session
for work nobody did.

Quote the product's own words in remarks where possible, and name concrete features ("the
payment page's three icon buttons") instead of abstractions.

## The issue list for the GSA supplement

Federal buyers may require the ACR Issue Detail Supplement that GSA's Section 508 program
describes at `https://www.section508.gov/sell/acr-supplement/`. Each issue has:

| Field | Value |
|---|---|
| `id`, `summary` | A label and one line saying what is wrong. |
| `criteria` | The row ids the issue affects. |
| `severity` | `Critical Accessibility Barrier` (prevents access to or completion of core functionality), `Major Accessibility Issue` (substantially impairs important functionality; a workaround exists) or `Minor Accessibility Issue` (usability friction or partial barriers; core tasks still complete). |
| `area` | The page, screen, component or flow, and how far the issue spreads. |
| `impacted_users` | One or more of the nine groups: Without Vision, With Limited Vision, Without Perception of Color, Without Hearing, With Limited Hearing, Without Speech, With Limited Manipulation, With Limited Reach and Strength, With Limited Language, Cognitive, and Learning Abilities. |
| `workaround` | The vendor-provided alternative, or `None known`. |

AccessLint's severity words map as follows when moving findings across: critical to Critical,
serious to Major, moderate and minor to Minor. Check each against the definitions above,
which decide.

`acr.py render` appends the issues as a section of the report, and `acr.py supplement`
writes them as CSV for pasting into GSA's workbook. Compare the CSV columns with the
workbook you download, since GSA publishes the workbook and can change it.

## Check kinds a person runs

`acr.py needs-human` prints a "usual check" beside each open row. The kinds, and what the
person does:

| Kind | The person |
|---|---|
| keyboard | Operates the product with the keyboard alone: reaches every control, sees the focus, leaves every component, completes the flows. |
| screen-reader | Uses a screen reader (and says which, with which browser) and listens to names, roles, states, headings, form errors and status messages. |
| visual | Looks at color, contrast, zoom to 200%, reflow at 320 CSS pixels, text spacing, focus indicators and layout. |
| media | Plays audio and video and checks captions, audio description, controls and flashing. |
| pointer | Uses mouse and touch: gestures, dragging, cancellation, target size. |
| content | Judges wording and flows: link purpose, labels, error suggestions, consistency across pages. |
| platform | Tests software against the platform's accessibility services. Not used for web products. |
| documentation | Reads the support documentation and tries the support services (Chapter 6). |

These hints are this skill's guidance on what usually settles a row. They are not part of
the VPAT, and a row can be settled by a different check when the evidence says so.

## What the script cannot decide

- Whether a failure is "some" or "the majority" of functionality. The author decides between
  Partially Supports and Does Not Support.
- Whether the sessions were sampled well. Say in `scope` what was covered, and say plainly in
  the report's Notes when the product has areas no session reached.
- Whether the report may be published, and whether the product conforms. Those belong to
  the people who sign for the company.
