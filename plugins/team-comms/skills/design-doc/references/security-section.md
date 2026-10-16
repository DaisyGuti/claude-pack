# Security and compliance section

## Contents

- [Rules for the section](#rules-for-the-section)
- [Data handled](#data-handled)
- [Trust boundaries](#trust-boundaries)
- [Controls touched](#controls-touched)
- [Threats considered](#threats-considered)
- [Designs that call a model API](#designs-that-call-a-model-api)
- [Gaps and unknowns](#gaps-and-unknowns)
- [Worked example](#worked-example)

## Rules for the section

1. **Evidence and gaps only.** The section lists what the design does, which controls it
   touches and what is not yet known. It never says the system is compliant, authorized,
   accredited or ready for an authorization decision. The program's security reviewer decides
   that. `doc_tool.py design check` flags sentences that do.
2. **Use the program's own labels.** Data classifications, impact levels and control
   families come from the program's documents (its system security plan, data handling
   policy or contract). Ask the user which document governs. Do not invent a scheme.
3. **Cite real IDs only.** Copy every control or criterion ID from the source document,
   opened now: for NIST SP 800-53 controls, the current catalog at
   https://csrc.nist.gov; for the program's baseline, its own plan. If you cannot open the
   source or are unsure of an ID, leave the ID out and write "ID to confirm" with the name
   of the control family or topic.
4. **Every subsection has content.** When a subsection does not apply, write one sentence
   that says why, such as "No personal data is stored; the service handles request metadata
   only."
5. **Facts about this design.** Generic advice ("use encryption") does not belong here. Say
   what the design encrypts, with what, where the key lives.
6. **Security review line.** Leave "not yet reviewed" until a named person reviews.

## Data handled

A table: each data element, its classification (program's label), where it is stored, and
where it flows. Include logs, caches, backups, analytics events and anything sent to a
third party. Mention retention and who can read each store. Flag any personal data, credentials, keys,
controlled or regulated information.

## Trust boundaries

List each place data or control crosses between components, accounts, networks, tenants or
people: user to edge, edge to service, service to database, service to a third party,
engineer to production. For each: how the caller is authenticated, how access is authorized,
and whether the data is encrypted in transit.

## Controls touched

A table with three columns: the control (ID copied from the source), the source document
and section, and how this design affects it (satisfies a part, changes how it is met,
needs new evidence, weakens it). Cover access control, audit logging, encryption,
configuration and change management, and supply chain when the design touches them. If the
program has not told the team which framework applies, write that as a gap and ask.

## Threats considered

A short list of threats weighed, each with the design's answer. Walk the trust boundaries
with these prompts: who could impersonate a caller; what could be altered in transit or at
rest; what actions lack a record; what could leak through logs, errors or caches; what
could be made unavailable; how a user could gain access beyond their role. For a deeper
model, use the security plugin from this marketplace and link its output.

## Designs that call a model API

If the design sends data to a model provider, add to this section: which data fields go in
each request; which provider and model and where it runs; whether the provider retains or
trains on the data and where that is documented; how model output is validated before
it acts on anything; how untrusted text in the input is kept from steering the model's tool
calls; and the cost and rate limits that apply. Look provider terms up now and cite them.

## Gaps and unknowns

Everything not yet known or not yet done, each with an owner: a control not yet
mapped, a data flow not yet reviewed, a decision waiting on the program office. A gap
listed here gets an owner and a date for closing it.

## Worked example

```markdown
## Security and compliance

### Data handled

| Data | Classification | Where it is stored | Where it flows |
| --- | --- | --- | --- |
| Uploaded files | Program label: Sensitive (confirm with the data owner) | Cloud Storage bucket `uploads-prod`, encrypted at rest | Browser to API gateway to upload service to bucket |
| Request metadata (user ID, size, time) | Internal | Postgres `audit` schema, 1 year retention | Upload service to Postgres |

### Trust boundaries

- Browser to API gateway: user session token, TLS.
- Upload service to bucket: workload identity with a write-only role.

### Controls touched

| Control | Source document | How this design affects it |
| --- | --- | --- |
| Audit logging (ID to confirm) | System security plan, audit section | Adds upload events to the audit log; retention unchanged |

### Threats considered

- A caller uploads a file to another user's path: object names are server-generated.

### Gaps and unknowns

- The data owner has not yet confirmed the classification of uploaded files (owner: Priya).
- Malware scanning of uploads is not designed yet (owner: platform team).

Security review: not yet reviewed
```
