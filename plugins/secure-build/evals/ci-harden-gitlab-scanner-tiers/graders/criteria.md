---
type: llm
---

PASS if the reply says which scanners need Ultimate and which produce at least a downloadable report on lower
tiers, names free alternatives for what is missing (for example osv-scanner or trivy for dependencies, semgrep
or gitleaks), and says the tier statements come from GitLab's current documentation or should be re-checked
there.

FAIL if it states that every scanner works fully on the Free plan, or gives tiers with no hint of checking
the current docs and no alternatives.
