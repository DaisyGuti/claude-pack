---
type: llm
---
PASS if the reply rewrites the prompt as a chain that (1) has a separate extraction prompt for each long document (both PDFs and the workbook at least), each writing the relevant excerpts to a notes file with a source location such as page, section, control ID, or sheet and row, (2) has a main prompt that works from those notes files, keeps the wiki page, the pull request and the README as inputs, and keeps the approve-before-commenting step, and (3) names a Claude model tier and an effort level for each stage.
FAIL if the rewrite is a single prompt that reads the documents whole, drops one of the inputs, has extraction notes without source locations, or gives no model and effort.
