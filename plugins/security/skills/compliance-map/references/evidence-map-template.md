# Evidence map template

Copy the skeleton into `docs/compliance/compliance-map-<YYYY-MM-DD>.md` and fill it in. Keep the
notice sentence and the heading words: `security_doc_check.py --kind compliance-map` looks for
them. Delete the guidance in angle brackets. The control IDs in the example rows show the format;
replace them with the controls you searched for.

````markdown
# Compliance evidence map: <system name>

This document lists evidence and gaps. It is not an assessment, and it does not state that the
system is compliant or authorized. Those decisions belong to the people with the authority to
make them.

- Date: <YYYY-MM-DD>
- Repository and revision: <name, commit>
- System boundary used: <what is in and out, as stated by the user or found in the docs>
- Assumptions: <for example "impact level not stated; mapped to the Moderate baseline">

## Summary

<Counts of rows by status, the three to five gaps that matter most, and the decisions a person
has to make. No statement about overall compliance.>

## Applicability

| Framework | Applies? | Basis | Who decides |
| --- | --- | --- | --- |
| FedRAMP | <Yes, Likely, No, Undetermined> | <fetched wording or fact from the repo> | <agency, contracting officer, system owner> |
| NIST SP 800-171 and CMMC | <...> | <...> | <...> |
| NIST SSDF and software attestation | <...> | <...> | <...> |
| DoD Cloud Computing SRG | <...> | <...> | <...> |
| FIPS 140-3 validated cryptography | <...> | <...> | <...> |
| SBOM expectations | <...> | <...> | <...> |

## Control evidence

Control set: <for example "NIST SP 800-53 Rev. 5 Moderate baseline, repository-observable subset">.

| Control | Title | Status | Evidence | Gap | Next step |
| --- | --- | --- | --- | --- | --- |
| AU-2 | Event Logging | Evidence found | `app/audit.py:18` lists sign-in, denial and export events | none found for the events checked | none |
| IA-2 | Identification and Authentication (Organizational Users) | Partial evidence | `auth/oidc.py:40` single sign-on | no multi-factor setting found | confirm identity provider policy |
| SC-13 | Cryptographic Protection | No evidence found | - | searched `crypto`, `hashlib`, `ssl` in `src/`; no FIPS mode setting | decide whether a validated module is required |
| PE-3 | Physical Access Control | Not assessable from repo | - | inherited from the cloud provider; cite its current authorization package | owner: operations |

## Cross-walk

### NIST SSDF practices

| Practice | Related 800-53 controls | Status | Evidence | Gap | Next step |
| --- | --- | --- | --- | --- | --- |
| <PW.x.y as printed in SP 800-218> | <controls from its References column> | <status word> | <evidence> | <gap> | <next step> |

### <FedRAMP KSIs, NIST SP 800-171 requirements, or DoD SRG items, one table each>

| Requirement | Related 800-53 controls | Status | Evidence | Gap | Next step |
| --- | --- | --- | --- | --- | --- |
| <ID exactly as printed in the fetched source> | <controls> | <status word> | <evidence> | <gap> | <next step> |

## Gaps and next steps

| Priority | Gap | Controls | Suggested action | Owner type |
| --- | --- | --- | --- | --- |
| 1 | <the gap> | <IDs> | <action> | <policy, engineering, operations, cloud provider> |

## Decisions for a person

- <Each decision the evidence cannot settle: impact level, whether CUI is present, whether a
  validated cryptographic module is required, whether the attestation is required by the contract.>

## Sources

| Source | URL | Version or date read |
| --- | --- | --- |
| NIST SP 800-53 Rev. 5 OSCAL catalog | https://github.com/usnistgov/oscal-content | replace with the version `nist_catalog.py fetch` printed |
| <FedRAMP consolidated rules> | https://github.com/FedRAMP/rules | <info.version and info.last_updated> |
````
