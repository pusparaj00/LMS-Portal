# Step 62: audit of steps 58 to 61, front end first (2026-10-20)

Branch `step-62-audit` (from `step-61-frontend-redesign`). Every check below was run; nothing is claimed that was not. Tools: axe-core 4.10 (loaded into a throwaway browser from a CDN, not added to the project), Playwright, the taste skill's `inspect.mjs` and `lint.mjs`, and the agent simulation from step 60.

## What was checked

| Check | How | Result |
| --- | --- | --- |
| Accessibility of the public pages | axe-core on the home and login pages, desktop light and phone dark | Contrast and the skip link failed; fixed (below); 0 violations after |
| Accessibility of the signed-in screens | axe-core on 13 student, 15 instructor and 2 admin routes, light and dark; plus the chat panel, the placement question and the problem page at phone width | Contrast, the calendar structure and the selected tab failed; fixed; 0 violations after, in both themes |
| Keyboard behaviour | Playwright: the live question, the phone menu, the assistant | Three problems found (menu, radio keys, no pause control), all fixed |
| Third-party requests | Listed every host each page contacts | Public pages: this origin only. Problem page: 13 requests to `cdn.jsdelivr.net` (the editor); fixed |
| Claims in `architecture.md` | Compared with the OpenAPI file and the live schema | Tables, migrations, roles correct; endpoint count was "about 146", the file has 147 path and method pairs (117 paths) |
| Regression run of the agent simulation on the code of steps 60 to 62 | 12 students x 14 steps, run twice | 0 server errors, 0 refusals that should have been allowed, 0 successes that should have been refused, 0 mastery changes by chat. The first run had 23 "connection refused" issues that were my own front-end rebuilds during the run; the second had 16 issues, all from reusing a stack whose accounts earlier runs had changed (a password reset by the admin check, work already turned in) plus the generic notes example the harness flags as fenced code. |

## Bugs found and fixed

1. **Low-contrast text across the whole app in light mode.** The new green accent (#0f7d45) was 4.2:1 on the ground; links, the active menu item, role badges and the "Live" status failed the 4.5:1 minimum on every signed-in page. Darkened to #0b6a3a (about 5:1).
2. **The selected tab was unreadable in dark mode** (to-do and to-review): dark text on a dark fill, 1.17:1. Selected tabs now use the accent fill with its own ink.
3. **Heatmap numbers failed contrast on 65 cells.** The class overview picked white or ink text by a fixed 55% cut, which fails in the middle of the scale and in dark mode. Text now flips between black and white by the cell's actual lightness in the current theme (crossover at lightness 49.6, where both give about 4.5:1). A first version of the rule produced mid-grey text for a cell right at the threshold (1.49:1); a sharper switch fixed it. Re-checked: 0 violations.
4. **The calendar grid had no row structure** (49 critical ARIA findings): a grid of header cells and cells without rows. Rows added. Outside-month dates were dimmed with opacity, which dimmed the due items in them too; only the date number is dimmed now, and the muted ink was raised.
5. **The phone menu stayed open after choosing a link**, covering the page. It closes now.
6. **The live question used `role="radio"` without arrow-key behaviour.** It is now a group of toggle buttons (`aria-pressed`).
7. **Moving text could not be stopped** (hero names, the highlighted concept): no pause control and no end. Both now run through once and stop, and a "Pause the moving words" button also pauses the logbook picture's drift.
8. **Escape did not close the assistant**, and focus was lost. It closes and focus returns to the "Ask the assistant" button.
9. **The skip link sat outside any landmark.** Moved into the header.
10. **The code editor loaded from a third-party CDN** on every problem page: the student's address went to jsDelivr (not named in the privacy notice), and the editor failed offline. It is now bundled from the `monaco-editor` package that was already a dependency, loaded on first use, with only the editor core and the Python language (the shipped front end is 6.8 MB; bundling everything came to 18 MB). Checked in a browser: no third-party host, typing, auto-indent, undo, Python highlighting and Run all work.
11. **The editor stayed white in dark mode.** It had no theme setting; it now follows the app theme, including when toggled.

## Smaller change

The front-end nginx now compresses text assets (the main script went from 820 KB to 276 KB over the wire) and caches the hashed files for a year; the page itself is not cached.

## Found and not changed

- An unknown address (for example `#/no-such-page`) shows the login page when signed out. There is no "page not found" view.
- The signed-in top bar still wraps to two rows on a phone.
- On a throwaway stack reused across several simulation runs, the admin password-reset check changes a student's password, so later runs cannot log that student in. That is a harness limit, not a product fault.
- The simulation harness's "fenced code" check flags the generic dictionary example from the course notes in the concept hint; the example is not the problem's solution (step 60).
- Not covered: the keyboard path through the closing sign-up sentence, screen-reader listening (axe checks rules, not what is heard), and Safari and Firefox (all checks ran in Chromium).
