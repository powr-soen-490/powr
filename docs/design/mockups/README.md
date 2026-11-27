# POWR hi-fi mockups

High-fidelity mockups of the POWR web app, designed in Canva ("Mockups - POWR", [view in Canva](https://www.canva.com/d/hZ3DfgDPUiAvLcl)) and exported as PNG at 1440 px wide. They build on the rough sketches in [`../sketches/`](../sketches/) the design foundations in [`../foundations/`](../foundations/), and the brand and UI proposal in [`../brand/`](../brand/), and show the dashboard with Mykonos Grill's data as the example restaurant.

| # | Screen | User story | File |
|---|---|---|---|
| 1 | Home (dashboard) | [#119](https://github.com/powr-soen-490/powr/issues/119) | [01-home.png](01-home.png) |
| 2 | Home, earlier version (kept to show how the design changed) | [#119](https://github.com/powr-soen-490/powr/issues/119) | [02-home-earlier-version.png](02-home-earlier-version.png) |
| 3 | Recommended orders | [#121](https://github.com/powr-soen-490/powr/issues/121), U-S #10 | [03-recommended-orders.png](03-recommended-orders.png) |
| 4 | Forecast | [#120](https://github.com/powr-soen-490/powr/issues/120), U-S #7 | [04-forecast.png](04-forecast.png) |
| 5 | Inventory & vendors | [#124](https://github.com/powr-soen-490/powr/issues/124), U-S #8 | [05-inventory-and-vendors.png](05-inventory-and-vendors.png) |
| 6 | Menu mapping | [#123](https://github.com/powr-soen-490/powr/issues/123), U-S #5 | [06-menu-mapping.png](06-menu-mapping.png) |
| 7 | Settings | [#122](https://github.com/powr-soen-490/powr/issues/122) | [07-settings.png](07-settings.png) |
| 8 | Log in | [#125](https://github.com/powr-soen-490/powr/issues/125), U-S #1 | [08-login.png](08-login.png) |
| 9 | Sign up (step 1 of 3) | [#125](https://github.com/powr-soen-490/powr/issues/125), U-S #1 | [09-sign-up.png](09-sign-up.png) |
| 10 | Toast connection (step 2 of 3) | [#49](https://github.com/powr-soen-490/powr/issues/49), U-S #3 | [10-toast-connection.png](10-toast-connection.png) |

## What the mockups show

- **Home:** what needs attention first (ingredients running out, orders to approve, unmapped dishes), and how POWR is doing: waste and cost avoided, forecast accuracy, food cost, ordered vs. used.
- **Recommended orders:** one order per supplier, built from the 14-day forecast and stock on hand. Each line says why, the manager can change any quantity, and nothing is sent until the order is approved.
- **Forecast:** ingredients that will run out this week, a daily usage chart, and when to reorder.
- **Inventory & vendors:** stock, pack sizes, prices and delivery times per vendor, with items missing details flagged.
- **Menu mapping:** dishes from Toast sorted by sales so the best sellers are mapped first, ingredients per order, and Toast modifiers ("no onions") linked to ingredients.
- **Settings:** restaurant and account, units (metric or US), light or dark theme, and email notifications.
- **Log in, sign up and Toast connection:** a three-step onboarding: create the account, connect Toast, map the best sellers.

## Stakeholder feedback

From the Release 1 walkthrough with John (Mykonos Grill, Nov 17, 2026):
- Menu mapping: items like soda don't need mapping. Shown: Toast extras such as "Add fountain soda" can be marked "Not an ingredient".
- Recommended orders: compare each order with previous ones (price change in %). Not in these mockups yet; planned for U-S #10.
- Menu mapping: sub-recipes for homemade items such as feta and tzatziki. Not in these mockups yet; planned for U-S #5.

To update these images, edit the Canva design, export each page as PNG, and replace the files with the same names.
