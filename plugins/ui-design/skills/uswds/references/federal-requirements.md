# Federal website requirements that USWDS supports

Read this when a task needs to say which federal rule applies to a web UI. Every statement
below was read from the primary source on the date given in "Sources". Anything that moves
(which website standards are required, the current WCAG version a memo points to, USWDS's
own accessibility position) is fetched when the skill runs, from the URL named in the
section.

## Contents

- [Who the rules bind](#who-the-rules-bind)
- [21st Century IDEA Act, section 3](#21st-century-idea-act-section-3)
- [OMB memorandum M-23-22](#omb-memorandum-m-23-22)
- [Federal website standards](#federal-website-standards)
- [Section 508](#section-508)
- [What USWDS says about its own accessibility](#what-uswds-says-about-its-own-accessibility)
- [How to report against these rules](#how-to-report-against-these-rules)
- [Sources](#sources)

## Who the rules bind

The Act and the memo are addressed to executive agencies. A company that builds a product
for an agency meets them through the contract, the agency's own policy and the agency's
review of the product. Before telling a team that a rule applies to its product, find out
which of three cases it is in: a public-facing agency website or digital service, an
internal tool, or a product sold to agencies that they run themselves. The answer is the
team's or the contracting officer's to give. Ask for it, and say which case the report
assumes.

## 21st Century IDEA Act, section 3

Public Law 115-336, enacted December 20, 2018. Section 3(a) says an executive agency that
creates or redesigns a public-facing website, web-based form, web-based application or
digital service "shall ensure to the greatest extent practicable" that it:

1. is accessible to individuals with disabilities in accordance with section 508 of the
   Rehabilitation Act of 1973 (29 U.S.C. 794d);
2. has a consistent appearance;
3. does not overlap with or duplicate legacy websites;
4. contains a search function that allows users to easily search content intended for
   public use;
5. is provided through an industry standard secure connection;
6. is designed around user needs with data-driven analysis, testing continually that user
   needs are addressed;
7. gives users the option for a more customized digital experience;
8. is fully functional and usable on common mobile devices.

Section 3(c) extends these requirements, to the greatest extent practicable, to an intranet
established after enactment. Section 3(e) says any agency website made available to the
public after enactment "shall be in compliance with the website standards of the
Technology Transformation Services of the General Services Administration." Those
standards are the ones published at standards.digital.gov (below).

## OMB memorandum M-23-22

"Delivering a Digital-First Public Experience," September 22, 2023. It rescinds M-17-06 and
guides agencies in implementing the Act. Points a UI team meets most often, with the
memo's own verbs:

| Topic | What the memo says |
|---|---|
| Accessibility | Agencies subject to Section 508 must comply with its standards. They "should apply the most current" WCAG to websites and web applications "where possible". A footnote says WCAG 2.1 was current when the memo was published, with 2.2 pending. |
| Accessibility testing | Agencies "should incorporate accessibility testing into website updates and release processes", including automated scanning, manual testing, usability testing with people with disabilities and testing with users of adaptive technologies. The memo states that automated tools "can only detect some accessibility issues". |
| Accessibility statement | Agencies "should develop and publish an accessibility statement that provides a public feedback mechanism". |
| USWDS and website standards | Agencies "should use" USWDS for a consistent appearance. "All public-facing websites and digital services must comply with the Federal website standards" published by GSA's Technology Transformation Services, which incorporate USWDS. |
| Domain | Agencies "generally must use a .gov or .mil domain name" for public-facing websites and digital services used for official communication. |
| HTTPS | Agencies "shall encrypt all web traffic" as HTTPS and preload their .gov and .mil domains as HTTPS-only (requirement carried from OMB M-22-09). |
| Authentication | Websites that require the public to sign in must work with commonly used password managers and must not prevent pasting passwords. Agencies must not require periodic password rotation. |
| Search | Public-facing websites "must contain a search function that allows users to easily search content intended for public use". |
| Mobile | "To the greatest extent practicable" public-facing sites must be mobile-friendly; mobile-first design is a "should". |
| Analytics | Agencies "are required to participate in" GSA's Digital Analytics Program. |

The memo scopes itself to websites and digital services, including web and mobile
applications, and says that the scope of Section 508 is broader and differs from the memo's.

## Federal website standards

Published at standards.digital.gov (they moved there from the USWDS site in September
2024). Each standard carries a status of research, draft, pending or required. The site
defines pending as finalized and "required after a specified time period" following its
move to pending. Fetch `https://standards.digital.gov/standards/` every time and report each
standard's status as read. Never rely on a status remembered from an earlier session.

Some standards describe facts a page either has or lacks (a government banner, an HTML
page title, a meta page description). `scripts/uswds_check.py page` reports those facts for
a template, and the fetched standard says which are pending or required.

## Section 508

The Revised 508 Standards require WCAG 2.0 Level A and AA for web content (E205.4) and for
software user interfaces (E207.2). Chapter 3 functional performance criteria apply to
functions that Chapters 4 and 5 do not address (E204.1). The text is at
`https://www.access-board.gov/ict/`. M-23-22 asks agencies to go further and apply the
most current WCAG where possible, so a buyer may ask for 2.1 or 2.2 on top of Section 508.

To produce an Accessibility Conformance Report for a USWDS-based product, use the
`section-508-report` skill in the `accessibility` plugin. USWDS evidence feeds it as
component-level input only (next section).

## What USWDS says about its own accessibility

Read `https://designsystem.digital.gov/documentation/accessibility/` when a report needs
to cite it. As read on the date below it says:

- USWDS targets WCAG 2.0 Level AA as the baseline (the Section 508 requirement) with
  WCAG 2.1 AA as the goal.
- "Building with accessible USWDS components does not guarantee an accessible service. You
  need to keep testing to stay accessible."
- It publishes an Accessibility Conformance Report on the VPAT format for the design
  system's components, and its component pages show an accessibility test status with a
  link to the test results.

That evidence covers USWDS's own components in USWDS's own test pages. It says nothing
about this product's content, custom components, color overrides or data. A product
report can cite it as supporting context for a row and still has to test the product.

## How to report against these rules

- State facts and gaps: "the template has no banner element; the fetched standard has the
  status pending". Never state that a product "meets the IDEA Act" or "is compliant". A
  person with authority decides that.
- Name the source and the date read for every federal claim.
- Separate what the code shows (a banner element exists) from what only a person can
  confirm (the domain is .gov, the contract requires the banner).

## Sources

Read on 2026-10-16:

- 21st Century Integrated Digital Experience Act, Pub. L. 115-336, section 3:
  https://www.congress.gov/115/plaws/publ336/PLAW-115publ336.htm
- OMB M-23-22, sections III.A.1 (accessibility), III.A.2 (design, domain), III.A.4 (search),
  III.A.5 (secure), III.A.6 (analytics), III.A.8 (mobile):
  https://bidenwhitehouse.archives.gov/wp-content/uploads/2023/09/M-23-22-Delivering-a-Digital-First-Public-Experience.pdf
- Federal website standards (status vocabulary): https://standards.digital.gov/standards/
- USWDS and the website standards, including the move to standards.digital.gov:
  https://designsystem.digital.gov/website-standards/
- USWDS accessibility documentation: https://designsystem.digital.gov/documentation/accessibility/
- Revised 508 Standards, E204.1, E205.4, E207.2: https://www.access-board.gov/ict/
