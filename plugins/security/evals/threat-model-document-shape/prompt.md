---
name: threat-model-document-shape
description: The threat model has a Mermaid diagram with a trust boundary, a ranked register and 800-53 control IDs.
tags: [output]
max_turns: 15
allowed_tools: [Read, Glob, Grep, Skill]
---

Threat model this design for me and put the whole document in your reply instead of writing a
file. A public web form posts a claim and a PDF to an API service. The API stores the record in a
SQL database and the PDF in a storage bucket, and a background worker reads the PDF and extracts
text with a third-party library. Staff review claims through an admin page that uses single
sign-on. Map each mitigation to NIST SP 800-53 Rev 5 controls.
