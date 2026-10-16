# Reviewing a USWDS page or component

A USWDS review checks that the implementation keeps the contract the design system
documents, and that the pieces outside USWDS (custom components, content, data) meet the
same bar. Work from the top. Stop at the first section that applies if the user asked a
narrow question.

## Contents

- [1. Run the script checks](#1-run-the-script-checks)
- [2. Compare each component with its documented markup](#2-compare-each-component-with-its-documented-markup)
- [3. Rules from the USWDS component pages](#3-rules-from-the-uswds-component-pages)
- [4. Styling and tokens](#4-styling-and-tokens)
- [5. Scripts and loading order](#5-scripts-and-loading-order)
- [6. Version and build](#6-version-and-build)
- [7. Federal website facts](#7-federal-website-facts)
- [8. What a review cannot decide](#8-what-a-review-cannot-decide)
- [Report shape](#report-shape)

## 1. Run the script checks

`uswds_check.py` is in this skill's `scripts/` folder (SKILL.md has the full command).

1. `classes --css <compiled uswds.css> <template folders>` lists `usa-` class names the
   stylesheet does not define: typos, classes removed by an upgrade, classes copied from
   another version's documentation. Each hit gets a fix or a stated reason (a class added
   only by JavaScript at run time).
2. `page <base layout or page files>` lists, per full HTML document, whether it has the
   `lang` attribute, a non-empty title, the viewport meta, a meta description, the skip
   link, the government banner, the initializer script and the library script.
3. `version --project .` compares the installed version with the latest on npm.

## 2. Compare each component with its documented markup

For every USWDS component in the diff or the page, fetch its page from
`https://designsystem.digital.gov/components/overview/` (follow the link for the component)
and compare the project's markup with the page's "Component code". Check:

- element types and order, and the class names on each element;
- required attributes (for the banner: the `aria-label` on the section, `aria-expanded`
  and `aria-controls` on the toggle button);
- ids that a `for`, `aria-controls` or `aria-describedby` points to exist exactly once;
- content was changed and structure was not.

Where the project changed the structure, record whether the component page's
"Accessibility guidance" still holds for the changed version.

## 3. Rules from the USWDS component pages

These come from USWDS's own guidance on the pages named. Fetch the page for the current
text, and treat a component page's wording as the rule when it differs from this list.

Forms (`components/form/`, `components/text-input/`):

- Controls appear in the HTML in the same order as on screen. No CSS reordering.
- Related controls sit in a `fieldset` with a single `legend`.
- Validation messages align visually with their inputs.
- Avoid placeholder text as a label substitute. Placeholder contrast is low and the text
  disappears when typing starts.
- Use one input for a number such as a phone number. Do not split it into a field per part.
- Avoid disabled text inputs. If a control must look unavailable, explain why next to it.
  A native `disabled` control leaves the tab order and is not submitted. `aria-disabled`
  alone only communicates the state, so application code must also block the action.
- Required fields are marked, with a text description of the marker at the top of the form
  and the `required` attribute. Optional fields in a form with required fields say
  "(optional)".
- An error summary or message names the field that failed, and the page title reflects the
  error for screen readers.

Buttons (`components/button/`):

- Use a `<button>` or a link with the `usa-button` class. A `<div>` or `<img>` used as a
  button is a finding.
- Always set `type` on a button (`submit`, `button` or `reset`). A missing `type` submits.
- A visible focus state appears on tab.

Banner (`components/banner/`):

- Use the provided text without customization.
- Do not use the banner on non-government domains.
- The `aria-label` on the banner section and the toggle's `aria-expanded` and
  `aria-controls` come from the component code.

## 4. Styling and tokens

- Colors, spacing, font sizes and font families come from tokens, utilities or theme
  settings. A literal value that duplicates a token is a finding.
- Project CSS that selects `.usa-*` classes changes a component. List each override and
  check it against that component's accessibility guidance, and measure contrast for any
  color it changes.
- A color pair is checked for contrast whether or not it uses tokens. USWDS grades its
  colors on one lightness scale across color families, and its color documentation
  (`design-tokens/color/overview/`) explains the contrast consequences. The measured WCAG
  ratio still decides.
- A utility class with no effect is often a responsive or state variant the project does
  not compile (see "Utilities and the grid" in `building-with-uswds.md`).

## 5. Scripts and loading order

- The initializer is in the `<head>` (or inlined) and the library is at the end of the
  `<body>`.
- USWDS JavaScript runs after the markup it controls exists.
- Interactive custom widgets follow the keyboard pattern on the matching ARIA Authoring
  Practices page. USWDS covers only its own components.

## 6. Version and build

- `package.json` pins `@uswds/uswds` to an exact version.
- The compiled CSS comes from the project's Sass build with the project's settings, or from
  the shipped `uswds.css`, and the choice is deliberate.
- Nothing edits `node_modules/@uswds/uswds`.

## 7. Federal website facts

Fetch `https://standards.digital.gov/standards/` and list each standard with the status
read there. Match each to a fact from `uswds_check.py page` or from the template. Report
"the template has no banner element, and the banner standard is pending" in that form. See
`federal-requirements.md` for what to say and what to leave to the contract.

## 8. What a review cannot decide

- Whether the product's domain and contract make a standard apply.
- Whether the page works with a screen reader, a keyboard and zoom. Those need a person,
  or the `accessibility` plugin's skills for a live page.
- Whether the product conforms to WCAG or Section 508. A review produces findings and
  gaps. The `section-508-report` skill turns audit evidence into a conformance report that
  states what is and is not evidenced.

## Report shape

```markdown
**Scope:** <files or pages reviewed, USWDS version read, date>

**Script checks:** <one line each for classes, page, version>

**Findings, worst first**
1. <file:line> | <rule and where it is documented> | <what the code does> | <the change>

**Federal website facts:** <standard, status read, what the code shows>

**Needs a person or a live test:** <items from section 8 that apply>
```
