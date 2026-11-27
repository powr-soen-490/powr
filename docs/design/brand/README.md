# POWR brand identity and Dashboard v2 UI proposal

[`POWR-UI-improvements-and-brand-identity.pdf`](POWR-UI-improvements-and-brand-identity.pdf) is the team's proposal for the Dashboard v2 design meeting ([#190](https://github.com/powr-soen-490/powr/issues/190)). It covers:

- **Why change:** 9 problems with the Release 1 dashboard (text-only menu, hidden POS sync status, alerts that all look the same, KPI cards without context, a chart with no scale or message, and more).
- **What we will change:** the v2 dashboard, problem by problem, plus a dark mode.
- **Brand rules:** colours, fonts, logo, pictures and how we write.
- **Icons:** a comparison of Phosphor, Hugeicons, Tabler, Iconoir, Untitled UI and Lucide, and a proposal to switch to Phosphor.
- **Animations and states:** allowed animations, plus loading, sync-failed and empty screens.
- **Other pages:** what to keep, change or remove on Orders, Forecast, Menu mapping, Inventory, Vendors, Settings and Login.
- **Decisions** for the meeting (In / Later / Out) and next steps.
- **Inspiration:** palette, logo, mood board and reference dashboards.

The hi-fi mockups that apply this proposal are in [`../mockups/`](../mockups/).

## Brand colours (as used in the mockups)

| Name | Hex | Use |
|---|---|---|
| Prussian Blue | `#14233A` | Left menu, titles, body text |
| Parchment | `#FAF7F1` | Page background (cards stay white) |
| Steel Azure | `#2A4A9B` | Main buttons, links, chart bars |
| Honey Bronze | `#D9A94F` | Details only: active page line, badges, bars. Never text on a light background |
| Blue Slate | `#566174` | Secondary text, chart labels |
| Turf Green | `#2F6B3F` | Good news: synced, going up, waste avoided |
| Brick Red | `#A63A2B` | Urgent alerts, items running out |

Fonts: **Playfair Display** for page titles, **Montserrat** for everything else, with tabular digits for numbers.

> Note: the colour table in the PDF lists the main blue as "Baltic Blue `#2A5A9B`". The palette image in the same PDF and the mockups use `#2A4A9B`, which is the value to build with.
