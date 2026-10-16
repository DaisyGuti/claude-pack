# Building with USWDS

How a project installs, compiles and uses the U.S. Web Design System. Each section names
the page to fetch for the current wording, because commands and defaults change between
releases. Everything here was read on 2026-10-16 from the package README for the version
published then and from the pages listed under "Sources".

## Contents

- [Install](#install)
- [Compile the Sass](#compile-the-sass)
- [Load the stylesheet, library and initializer](#load-the-stylesheet-library-and-initializer)
- [Components](#components)
- [Design tokens](#design-tokens)
- [Utilities and the grid](#utilities-and-the-grid)
- [Page templates and patterns](#page-templates-and-patterns)
- [Updating a version](#updating-a-version)
- [Sources](#sources)

## Install

The package is `@uswds/uswds`. The developer install page says to pin it:

```sh
npm install @uswds/uswds --save-exact
```

`--save-exact` "pins the dependency to an exact version until you manually update it,
which reduces the risk of a USWDS update unexpectedly breaking or changing your project."
The source lands in `node_modules/@uswds/uswds`. Do not edit anything inside
`node_modules`, because the next install overwrites it; customize through the project's
own Sass settings. `scripts/uswds_check.py version` reports the installed version against
the latest on npm and notes when `package.json` declares a range.

The package holds compiled assets in `dist/` (`css/uswds.css`, `js/uswds.js`,
`js/uswds-init.js`, `fonts/`, `img/` with the icon `sprite.svg`) and component sources
in `packages/usa-<component>/`. Fonts and icons ship inside the package.

## Compile the Sass

Most projects compile their own CSS from the USWDS Sass so that theme settings apply. The
compile page documents two routes.

1. **`@uswds/compile`** (a dev dependency) with a `gulpfile.js` that sets
   `uswds.settings.version = 3`, optional `uswds.paths.dist.*` folders and exports
   `init`, `compile` and `watch`. `npx gulp init` copies the assets, adds a Sass entry
   point and compiles once; `npx gulp compile` rebuilds the CSS.
2. **Your own Sass compiler.** An entry file forwards the project's settings first, then
   USWDS, then the project's own styles:

   ```scss
   @forward "uswds-theme.scss";
   @forward "./path/to/source/uswds";
   @forward "project-styles.scss";
   ```

Fetch `https://designsystem.digital.gov/documentation/getting-started/developers/phase-two-compile/`
for the current steps, and `.../phase-three-customize/` for theme settings.

## Load the stylesheet, library and initializer

The package README names three files that most projects need on every page:

- the compiled **stylesheet** in the `<head>`;
- the **initializer** `uswds-init.min.js` in the `<head>` (or inlined), which keeps
  component content from flashing or shifting while the library loads;
- the **library** `uswds.min.js` at the end of the `<body>`, which makes components
  interactive.

A component package that ships an `src/index.js` carries JavaScript behavior that the
library provides. In the package read for this file those include the accordion, banner,
combo box, date picker, header, modal, tooltip and validation. A component whose markup is
correct but does nothing is usually missing the library script, or the page loads it before
the markup it controls.

## Components

Each component has a page at `https://designsystem.digital.gov/components/<name>/`.
Fetch `https://designsystem.digital.gov/components/overview/` for the current list of
names instead of relying on a remembered list. A component page carries:

- **Component code**: the HTML to copy. Use it as given: change the content and leave the structure alone.
  The classes, attributes and element order encode the accessibility behavior.
- **Guidance**: when to use the component and when to consider something else.
- **Accessibility guidance**: what to keep true when customizing, such as avoiding
  placeholder text in text inputs or keeping a visible label.
- **Accessibility test status**: the count of USWDS's own WCAG tests and a link to
  `.../components/<name>/accessibility-tests/` with the individual results.
- **Package and latest updates**: the Sass package to forward, and a dated table of
  changes that says when a change is breaking.

When a task asks for a component that is not in USWDS, build it from tokens and
utilities, and check the new piece against the closest component's accessibility
guidance.

## Design tokens

Tokens are the predefined units the system builds from. The design tokens page groups
them as color, typesetting, spacing units, flex, opacity, order, shadow and z-index.
Reference a token three ways:

- Sass functions that return a value: `color('primary-vivid')`, `units(0.5)`,
  `size('sans', '3xs')`, `family('body')`;
- mixins that set properties: `u-padding-x(2)`, `u-font('ui', 'lg')`, `u-bg('white')`;
- utility classes: `.padding-x-05`, `.border-red`, `.font-family-sans`.

A literal hex color or pixel padding in project CSS that duplicates a token is a review
finding: it drifts when the theme changes.

## Utilities and the grid

Utilities are single-purpose classes named `[base]-[value]`, for example
`margin-top-2`, drawn from the project's theme tokens. Some come in responsive and state
variants, written as a prefix: `tablet:grid-col-6`, `hover:bg-green`. Breakpoints are
mobile-first minimum widths, so `tablet:grid-col-4` applies from the tablet width upward.

Which variants exist depends on the Sass settings, because the build only outputs the
breakpoints and states it is configured for. A utility that has no effect is often a
variant the project never compiled. Check with:

```sh
uswds_check.py classes --css <compiled uswds.css> \
  --prefix '^(tablet|desktop|mobile-lg|hover):' <templates>
```

SKILL.md gives the full path to the script.

The layout grid uses `grid-container`, `grid-row` and `grid-col-*` (with responsive
prefixes). Columns are full width until the narrowest breakpoint named in a `grid-col`
class.

## Page templates and patterns

`https://designsystem.digital.gov/templates/` holds page templates, which are common
component combinations built on the default theme and meant as a starting point.
`https://designsystem.digital.gov/patterns/` holds patterns, which are practical guidelines
for common user interactions. Both lists change, so fetch them and read what is there.
Start a new page from the nearest template, and check the patterns page when a task is a
flow (a long form, a language choice, a profile) before inventing one.

## Updating a version

Read the dated release notes at `https://github.com/uswds/uswds/releases` and the
"latest updates" tables on the component pages you use before changing the pinned
version. For a major version change, read the migration guide at
`https://designsystem.digital.gov/documentation/migration/` first. After an update,
re-run `scripts/uswds_check.py classes` over the templates: it finds class names that a
newer stylesheet no longer defines.

## Sources

- Install: https://designsystem.digital.gov/documentation/getting-started/developers/phase-one-install/
- Compile: https://designsystem.digital.gov/documentation/getting-started/developers/phase-two-compile/
- Package README (directory layout, stylesheet, library, initializer): the `README.md` in
  `@uswds/uswds`, also at https://github.com/uswds/uswds
- Design tokens: https://designsystem.digital.gov/design-tokens/
- Utilities: https://designsystem.digital.gov/utilities/
- Layout grid: https://designsystem.digital.gov/utilities/layout-grid/
- Components: https://designsystem.digital.gov/components/overview/
- Text input (an example of the component page layout):
  https://designsystem.digital.gov/components/text-input/
- Banner: https://designsystem.digital.gov/components/banner/
