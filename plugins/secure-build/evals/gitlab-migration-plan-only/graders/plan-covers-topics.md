---
type: regex
pattern: '^(?=.*cutover)(?=.*rollback)(?=.*importer)(?=.*(Workload Identity|WIF))(?=.*CODEOWNERS)(?=.*(Renovate|osv-scanner|trivy|dependency scanning))(?=.*Slack)(?=.*(\.gitlab-ci\.yml|id_tokens))'
flags: is
match: contains
target: last_message
---
