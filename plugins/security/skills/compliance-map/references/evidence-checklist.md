# Evidence checklist: 800-53 controls a repository can show

Contents:
- Rules for recording evidence
- Access control and identity
- Audit and accountability
- System and communications protection
- System and information integrity
- Configuration, change and supply chain
- Development process and assessment
- Settings that live outside the files

Use this list to decide which controls to search for. It names where evidence usually sits. The
catalog and the framework text state what each control requires; read the requirement there
before judging a gap. Controls missing from this list (physical, personnel, most of incident
response and contingency planning) are `Not assessable from repo`: name the kind of owner who can
answer (policy owner, operations, HR, the cloud provider).

## Rules for recording evidence

- Cite `path:line` for code and configuration, a document path and heading for prose, and a
  command and its output for a setting read from a live system.
- Open the file and read the line. A file name or a library import is not evidence that a
  control works.
- Quote at most one line. Never copy a secret, a token or personal data into the report.
- `Evidence found` means the repository shows the control element in place for what you checked.
  `Partial evidence` means some elements are there and some are missing; say which in the Gap
  column. `No evidence found` means you searched and list where you looked. `Not assessable from
  repo` means the repository could not hold the evidence.
- Record the search you ran in the Gap or Next step column for every `No evidence found`, so the
  reader can repeat it.

## Access control and identity

| Control | Look for | Usual places |
| --- | --- | --- |
| AC-2 Account Management | account creation, removal and review flows; service accounts with named owners; identity provider setup | auth module, admin code, IAM Terraform, runbooks |
| AC-3 Access Enforcement | a server-side authorization check on every route and object, deny by default | middleware, route guards, policy files, tests that assert 403 |
| AC-4 Information Flow Enforcement | egress limits, network policies, allowlists between tiers | VPC firewall rules, Kubernetes NetworkPolicy, proxy config |
| AC-6 Least Privilege | narrow IAM roles, no wildcard permissions, non-root containers, separate admin paths | IAM Terraform, Dockerfile `USER`, role definitions |
| AC-7 Unsuccessful Logon Attempts | lockout or throttling after failed sign-ins | auth code, identity provider policy |
| AC-8 System Use Notification | a use-notification banner before sign-in | login templates |
| AC-11 Device Lock, AC-12 Session Termination | idle and absolute session timeouts, server-side invalidation on logout | session configuration |
| IA-2 Identification and Authentication (Organizational Users) | multi-factor authentication, single sign-on integration, no shared accounts | auth config, identity provider settings |
| IA-5 Authenticator Management | password or token rules, secret storage and rotation, no credentials in the repo | secrets configuration, gitleaks result from `security-scan` |
| IA-8 Identification and Authentication (Non-organizational Users) | federation or proofing for outside users | sign-up and login flows |

## Audit and accountability

| Control | Look for | Usual places |
| --- | --- | --- |
| AU-2 Event Logging | the list of events logged: sign-in success and failure, authorization denial, privilege change, data export, admin action | audit module, logging config, design docs |
| AU-3 Content of Audit Records | each record carries event type, time, source, outcome and identity | log formatter, schema |
| AU-8 Time Stamps | UTC time stamps, a defined time source | logger config, base image time sync |
| AU-9 Protection of Audit Information | restricted write and read access, separate storage, retention lock | log sink and bucket Terraform |
| AU-11 Audit Record Retention | configured retention period | bucket lifecycle rules |
| AU-12 Audit Record Generation | the code paths for the AU-2 events actually emit a record | audit calls, tests |

## System and communications protection

| Control | Look for | Usual places |
| --- | --- | --- |
| SC-5 Denial-of-service Protection | rate limits, quotas, autoscaling limits | gateway and load balancer config |
| SC-7 Boundary Protection | restricted ingress, private services, no public buckets or open firewall rules | firewall and load balancer Terraform, ingress manifests |
| SC-8 Transmission Confidentiality and Integrity | TLS 1.2 or later on every connection, HSTS, certificate validation left on, no plaintext protocols | server and ingress config, connection strings, HTTP client settings |
| SC-12 Cryptographic Key Establishment and Management | a key management service, rotation, no keys in the repo | KMS Terraform, key config |
| SC-13 Cryptographic Protection | algorithms and libraries used; whether a FIPS mode or validated provider is enabled; weak algorithms (MD5 or SHA-1 for security, DES, RC4, ECB) | crypto calls, build flags, base images, runtime flags |
| SC-17 Public Key Infrastructure Certificates | certificate issuance and renewal | certificate manager config |
| SC-23 Session Authenticity | random session identifiers, cookie flags, CSRF defense | session and cookie code |
| SC-28 Protection of Information at Rest | encryption at rest for databases and storage, customer-managed keys where required | storage and database Terraform |

## System and information integrity

| Control | Look for | Usual places |
| --- | --- | --- |
| SI-2 Flaw Remediation | dependency update automation, a patch timeline, scans that gate merges | Dependabot or Renovate config, CI jobs |
| SI-4 System Monitoring | alerting rules, log analytics, intrusion detection | monitoring config |
| SI-7 Software, Firmware, and Information Integrity | signed commits, images or artifacts; checksum or signature verification | CI signing steps, release scripts |
| SI-10 Information Input Validation | schema validation, parameterized queries, output encoding | request handling layer, tests |
| SI-11 Error Handling | no stack traces or internals returned to users, errors logged | error handlers |
| SI-12 Information Management and Retention | retention and deletion of data | jobs, policies |

## Configuration, change and supply chain

| Control | Look for | Usual places |
| --- | --- | --- |
| CM-2 Baseline Configuration | infrastructure and images defined as code, pinned versions | Terraform, Dockerfiles, lockfiles |
| CM-3 Configuration Change Control | required review, protected branches, CI gates before merge | CODEOWNERS, workflow or pipeline files, repository settings (see the last section) |
| CM-6 Configuration Settings | hardened defaults, debug off in production | config files, Helm values |
| CM-7 Least Functionality | minimal images, unused ports and services disabled | Dockerfiles, manifests |
| CM-8 System Component Inventory | an SBOM, dependency lockfiles | SBOM output (produced by `secure-build`), lockfiles |
| SR-3 Supply Chain Controls and Processes | dependency sourcing rules, a private mirror or registry | package manager config |
| SR-4 Provenance | build provenance attestations | CI attestation steps |
| SR-11 Component Authenticity | hash-pinned dependencies, signature verification | lockfiles with hashes, verification steps |
| SA-22 Unsupported System Components | runtimes and libraries past end of support | base images, language version files |

## Development process and assessment

| Control | Look for | Usual places |
| --- | --- | --- |
| SA-3 System Development Life Cycle | a written development process | contributing guide, process docs |
| SA-8 Security and Privacy Engineering Principles | design decisions that cite security principles | architecture decision records, threat models (from `threat-model`) |
| SA-10 Developer Configuration Management | version control with history, change tracking | repository, tickets |
| SA-11 Developer Testing and Evaluation | security tests and static analysis run in CI | test suites, CI jobs, `security-scan` reports |
| SA-15 Development Process, Standards, and Tools | the toolchain and standards the team uses | CI config, lint config |
| SA-17 Developer Security and Privacy Architecture and Design | an architecture document that shows boundaries and data flows | design docs, threat models |
| RA-3 Risk Assessment | a risk or threat assessment | threat models |
| RA-5 Vulnerability Monitoring and Scanning | scanners in CI with triage of results | CI jobs, `security-scan` reports |
| CA-7 Continuous Monitoring | scheduled scans and dashboards | scheduled pipelines |
| CA-8 Penetration Testing | penetration test reports | docs folder |
| PL-2 System Security and Privacy Plans | a system security plan | docs folder |
| IR-4 Incident Handling, IR-6 Incident Reporting | incident runbooks and contact paths | runbooks |

## Settings that live outside the files

Branch protection, required reviews and merge rules are settings of the hosting platform, so
the repository files alone cannot show them. Read them from the platform when the user allows it,
and record the command and its output as evidence.

| Platform | Command |
| --- | --- |
| GitHub | `gh api repos/{owner}/{repo}/branches/{branch}/protection` and `gh api repos/{owner}/{repo}/rulesets` |
| GitLab | `glab api projects/:id/protected_branches` and `glab api projects/:id/approval_rules` |

If you cannot run them, mark the related row `Not assessable from repo` and give the command in
the Next step column. Pipeline definitions are in the files: `.github/workflows/*.yml` for GitHub
Actions and `.gitlab-ci.yml` for GitLab CI.
