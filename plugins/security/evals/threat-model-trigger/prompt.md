---
name: threat-model-trigger
description: A design-stage request should load the threat-model skill.
tags: [trigger]
max_turns: 12
allowed_tools: [Read, Glob, Grep, Skill]
---

We are about to build a feature that lets claimants upload supporting documents to our claims
portal. It runs on Google Cloud behind a load balancer, with Cloud Run for the API and Cloud SQL
for the records. Before we write any code, work out how an attacker could abuse this and what we
should build to stop it.
