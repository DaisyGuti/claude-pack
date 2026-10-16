# Report template

Write the report to a file named `model-usage-audit-<date>.md` in the folder the user chooses
(the current folder by default), and say where it is. Fill every section; write "None found"
for an empty one and "Not checked: <reason>" for anything the audit could not examine.

## Contents

- Template
- Writing the findings

## Template

````markdown
# Model usage audit: <product or repository>

Date: <today>. Scope: <paths scanned, services covered, anything left out and why>.
Method: inventory script over the tree, then a read of each call site, then checks against
provider pages fetched on the date above.

## Summary

<Three to six sentences: how many call paths, which providers and routes, the most important
findings, and the first three things to fix.>

| Severity | Findings |
|---|---|
| Critical | <ids> |
| High | <ids> |
| Medium | <ids> |
| Low | <ids> |

## Call paths

| ID | Path (entry point, file:line) | Provider and route | Model id (as found) | Pinned? | User-facing? | Data in the prompt | Stored or logged? |
|---|---|---|---|---|---|---|---|

## Findings

### F1 <title> (<severity>)

- **Evidence:** `path/to/file.py:42` <what the code does, quoted briefly>.
- **Why it matters:** <one or two sentences, with the source page if it rests on a provider fact>.
- **Fix:** <the change, small enough to act on; include the replacement id or setting>.
- **Effort:** <hours or days, a rough guess is fine>.

## Model lifecycle

| Model id | Where used (file:line) | Status | Retirement date | Source and fetch date | Replacement |
|---|---|---|---|---|---|

## Cost by call path

| Path | Model | Input tokens per call (cached / uncached) | Output tokens per call | Calls per day | Price used (source, date) | Monthly estimate |
|---|---|---|---|---|---|---|

Assumptions: <how each number was obtained: measured from logs, counted, or estimated>.

## Data flow and authorization evidence

| Route | Region or endpoint | Data classes sent | Retention and training terms (source, date) | Authorization evidence found (source, date) | Gap or question for the vendor |
|---|---|---|---|---|---|

This section lists evidence and gaps. It does not state that any route is compliant or
authorized. The person who holds that authority decides.

## Secrets and access

<Findings from the inventory and the read of config: keys in files, tracked env files, client-side keys,
credential type per route, rotation.>

## Eval coverage

| Call path | Eval exists | Runs when | Covers refusals and bad input | Data safe to store |
|---|---|---|---|---|

## Fix plan

1. <Critical and High items first, with an owner suggestion and the order that avoids rework.>
2. <Quick wins: caching, a smaller model on mechanical paths, centralizing model ids.>
3. <Items that need a decision from someone else, with the question to ask.>

## What was not covered

<Prompts held outside the repo, gateways defined elsewhere, services in other repositories, pages that could not
be fetched, code that could not be read.>
````

## Writing the findings

- One finding, one change. Split a finding when its fixes have different owners.
- Evidence first: a reader should be able to open the file and see the problem.
- Say how sure you are when the code leaves room: "appears to", with the part still unchecked.
- Never paste a secret, a customer record or prompt text containing personal data into the
  report. Give file:line and the kind of data.
- Order findings by severity, then by how cheap the fix is.
