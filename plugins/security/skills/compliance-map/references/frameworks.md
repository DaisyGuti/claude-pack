# Frameworks, what decides applicability, and what to fetch

Contents:
- How to use this file
- NIST SP 800-53 Rev. 5 (the common language)
- FedRAMP
- DoD Cloud Computing SRG
- NIST SP 800-171 and CMMC
- NIST SSDF (SP 800-218) and the software attestation
- FIPS 140-3 cryptography
- SBOM and Executive Order 14028
- Google Cloud inheritance
- Fetch checklist

## How to use this file

Every framework below changes on its own schedule: baselines are revised, programs pause or
start, deadlines move. This file therefore holds only what is stable (what each framework is
for, who decides whether it applies, where the authoritative text lives) and tells you what to
fetch. Fetch the source in the same run, record its version or date in the report's Sources
table, and prefer the fetched text over anything remembered, including this file.

When a source cannot be fetched, write `source not obtained` in the Sources table and mark every
row that depends on it `Not assessable from repo`. Do not fill the gap from memory.

## NIST SP 800-53 Rev. 5 (the common language)

FedRAMP, the DoD Cloud Computing SRG and NIST SP 800-171 all rest on 800-53 controls, so the
report collects evidence once per 800-53 control and cross-walks outward.

- Catalog and the Low, Moderate and High baselines come as OSCAL JSON. Fetch and query them with
  `nist_catalog.py` (`fetch`, `show`, `baseline`). The script prints the catalog version it
  fetched; copy that into the Sources table.
- The baselines are defined in NIST SP 800-53B: https://csrc.nist.gov/pubs/sp/800/53/b/upd1/final.
  An agency picks the baseline from the FIPS 199 impact categorization of its system.
  The system owner or the agency decides the impact level. Do not choose one on their behalf;
  if it is not stated, produce the map against the Moderate baseline and say that was an
  assumption.
- Control text: https://csrc.nist.gov/pubs/sp/800/53/r5/upd1/final

## FedRAMP

FedRAMP applies to cloud services that create, collect, process, store or maintain federal
information on behalf of an agency. Whether a given use is in scope is the agency's decision,
and a system used by a single agency may be outside FedRAMP altogether.

FedRAMP publishes its current rules as the Consolidated Rules. The machine-readable source and
the narrative source are the two places to read. Fetch:

1. `https://raw.githubusercontent.com/FedRAMP/rules/main/fedramp-consolidated-rules.json`
   Read `info.version` and `info.last_updated` and record them. Its `CTL` section carries
   FedRAMP's parameter values and guidance per control, and its `KSI` section holds the Key
   Security Indicators. The repository's `AGENTS.md` explains the layout. Parse it with a JSON
   parser; the rendered website is meant for people.
2. Narrative pages in https://github.com/FedRAMP/2026-markdown (raw files under
   `https://raw.githubusercontent.com/FedRAMP/2026-markdown/main/`):
   - `providers/start/path.md` for the certification paths and types, including whether FedRAMP
     20x or Rev5 is available for the product's situation;
   - `providers/start/class.md` for the certification classes and how they relate to Low,
     Moderate and High;
   - `timeline.md` for effective dates and what is open now;
   - `scope.md` for what is inside FedRAMP's scope.
3. FedRAMP marks its earlier document set (the `FedRAMP/docs-legacy` repository, including the
   baseline workbook in it) as historical reference only. Do not use it.

State in the report, with the fetched wording as the basis:
- whether FedRAMP applies to this product (an agency decision; say who decides);
- whether FedRAMP 20x applies, and which type and class the product's situation points to;
- how the class relates to an impact level (FedRAMP says the two do not line up one to one, so do
  not present a class as an impact level);
- the control set used for the map (the 800-53B baseline plus FedRAMP's parameters from `CTL`).

For 20x, collect evidence per indicator under `KSI.<theme>.indicators`, using the indicator IDs
exactly as the JSON gives them.

## DoD Cloud Computing SRG

Applies when a product or a hosting environment serves the Department of Defense. The guide sets
the impact levels, the controls and parameters each level needs, the split between the cloud
provider and the mission owner, and the provisional authorization process run by DISA.

- Find the current Cloud Computing Security Requirements Guide and its date through the DoD Cyber
  Exchange: https://www.cyber.mil/dccs/dccs-documents/ (the page is rendered by script, so a plain
  fetch may return nothing; search for the document title and read the PDF).
- The impact level for a system comes from the mission owner's categorization. Ask the user or
  find it in the contract. If it is unknown, write `impact level undetermined` and map to the
  800-53 baseline only.

## NIST SP 800-171 and CMMC

NIST SP 800-171 protects controlled unclassified information (CUI) in non-federal systems. DoD
contracts reach it through the CMMC program, defined by 32 CFR Part 170.

- Read 32 CFR Part 170 for the program's current text, and the DoD CIO's CMMC pages for its
  phase-in and any announced changes: https://www.ecfr.gov/current/title-32/subtitle-A/chapter-I/subchapter-G/part-170
  and https://dodcio.defense.gov/CMMC/.
- Confirm which revision of SP 800-171 the program requires today. Two revisions exist, with
  different requirement IDs. Fetch the one in force:
  https://csrc.nist.gov/pubs/sp/800/171/r2/upd1/final and
  https://csrc.nist.gov/pubs/sp/800/171/r3/final.
- Take requirement IDs and the 800-53 mapping from the SP itself, which carries a mapping
  appendix. Cite IDs exactly as printed there.
- Whether CUI is present at all is a contract and data-marking question. Do not infer it.

## NIST SSDF (SP 800-218) and the software attestation

The Secure Software Development Framework lists secure development practices in four groups:
Prepare the Organization (PO), Protect the Software (PS), Produce Well-Secured Software (PW) and
Respond to Vulnerabilities (RV).

- Current version and status: https://csrc.nist.gov/projects/ssdf. Table 1 of the SP lists each
  practice with references, including the SP 800-53 controls it relates to. Use that column for
  the cross-walk, and cite practice IDs exactly as printed in the version you fetched.
- The CISA Secure Software Development Attestation Form:
  https://www.cisa.gov/resources-tools/resources/secure-software-development-attestation-form.
  OMB memorandum M-26-05 (January 23, 2026) rescinded M-22-18 and M-23-16, the memos that
  required agencies to collect it. Agencies may still choose to use the form or ask for an SBOM
  by contract. Source: https://www.whitehouse.gov/wp-content/uploads/2026/01/M-26-05-Adopting-a-Risk-based-Approach-to-Software-and-Hardware-Security.pdf.
  Confirm nothing newer has replaced it. Then treat the attestation as a requirement only when the
  customer's contract or solicitation names it.
- When it is required, map evidence to each attestation statement on the form you fetched. The
  form is signed by the company official it names. The map supplies evidence for the statements,
  and that person decides whether to sign.

## FIPS 140-3 cryptography

800-53 control SC-13 and IA-7 are where validated cryptography shows up. Federal use points to
modules validated under the Cryptographic Module Validation Program.

- Read the program page for the current validation standards and any transition dates for
  older certificates: https://csrc.nist.gov/projects/cryptographic-module-validation-program.
  Search validated modules at the program's validated modules search.
- Evidence the repository can show: which cryptographic library and version the code calls,
  whether a FIPS mode or validated-provider setting is switched on in code, build flags,
  base images and runtime configuration, and where keys live.
- Evidence it cannot show: that a module holds a current certificate. Give the module name and
  version so a person can look up the certificate and read its security policy. A library
  "based on" or "compatible with" a validated module is not itself validated. Say so.

## SBOM and Executive Order 14028

Executive Order 14028 (May 2021) started the federal push on software supply chain security. It
may have been amended, and the OMB memos that implemented it have changed, so read the current
text on federalregister.gov and the CISA SBOM page (https://www.cisa.gov/sbom) before writing a
statement about what is required. Today an SBOM is generally an agency or contract term. For a
cloud service an agency may ask for an SBOM of the production runtime.

This skill records whether the repository produces an SBOM, in which format and where it is
published. Producing one is the `secure-build` plugin's job.

## Google Cloud inheritance

The team builds on Google Cloud first. A control the cloud provider operates (physical security,
hypervisor, parts of the network) is inherited from the provider's authorization package, and the
repository cannot show it.

- Mark an inherited control `Not assessable from repo` and write in the Gap column: "inherited
  from the cloud provider; cite its current authorization package".
- Where the repository's Terraform sets controls the customer owns (organization policies,
  encryption keys, private access, logging sinks, Assured Workloads folders), cite the file and
  line as evidence.
- Provider compliance offerings and authorization status:
  https://cloud.google.com/security/compliance and https://cloud.google.com/assured-workloads.

## Fetch checklist

Before writing the report, fetch what the applicable frameworks need and note each source and its
version or date in the Sources table.

| Need | Source |
| --- | --- |
| 800-53 catalog and baselines | `nist_catalog.py fetch --dest "${CLAUDE_PLUGIN_DATA}/nist"` |
| FedRAMP rules, KSIs and parameters | FedRAMP/rules JSON, FedRAMP/2026-markdown pages |
| DoD impact levels | DoD CC SRG from the DoD Cyber Exchange |
| CMMC and 800-171 revision in force | 32 CFR Part 170, DoD CIO CMMC page, SP 800-171 |
| SSDF practices and references | SP 800-218 from the NIST SSDF project page |
| Attestation status | OMB M-26-05 and the CISA form page |
| Cryptographic module rules | NIST CMVP page |
| SBOM expectations | CISA SBOM page and the customer's contract |
