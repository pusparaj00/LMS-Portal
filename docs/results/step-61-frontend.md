# Step 61: frontend redesign (2026-10-20)

Branch `step-61-frontend-redesign` (from `step-60-simulation-architecture`). Skills used: `design-taste-frontend` (tasteskill, with its draw, assets, lint and inspect scripts), `redesign-existing-projects` and `uiux-direction`. Scope chosen by the owner: public site first, then the logged-in app; text face everywhere with monospace only for code; found, credited archive pictures plus real interface fragments.

## What changed

| Area | Change |
| --- | --- |
| Direction | Dealt by `draw.mjs` (seed 482348421): "the sentence is the layout", chosen over type-only and colour-chapters because a poster-scale sentence can carry one element from the subject. Idea: *a wrong answer to a real tracing question becomes the named misconception it came from.* The blank in "Every error has a ___." cycles through real misconception names from `data/bank/misconceptions.json`. |
| Live thing | A real tracing question from `data/bank/items.json` (three of them) on the public page. A wrong option names its misconception and shows the bank's description. Nothing is sent anywhere and the page says so. |
| Public site (`pages/HomePage.tsx`, `pages/home/*`) | Rebuilt: two-field hero, the live question, a bar showing the four stages of a failed submission (run, explain, check, show) sized by what each can take, the 1947 logbook picture, feature rows on one axis with archive pictures, the twelve concepts, a status table, six FAQ answers, a closing sentence whose blank is the sign-up email, and a footer with the cropped name. Colour by chapter; the top bar takes the ink of the chapter beneath it. |
| Content fixed on the way | The old page said "up to 10 questions ... stop early" (the test is 16 to 20 questions with no early stop since step 56), listed "Admin pages for model and runner settings" as planned, and omitted quizzes, hand-in work, rubrics, to-do, calendar and notifications. The status table now follows `docs/results/verification-status-2026-10-20.md` and says plainly that a pilot with real students, people rating explanations, email and Canvas are not done. The FAQ says most explanations in a recent simulated test ended as plain hints. |
| Pictures | Five public-domain images from Wikimedia Commons, downloaded with `assets.mjs` into `frontend/public/archive/`, credited in the footer and in `credits.json`: the 1947 "first computer bug" logbook page, Lovelace's Note G, her portrait, two women operating ENIAC, an 1895 Hollerith card. They show the history of the subject, never the product. |
| Tokens and type (whole app) | New warm palette (rose grey ground, brown-black ink, one green accent) in the existing token names, with a matching dark theme. Bricolage Grotesque for all text; JetBrains Mono only for code, test output and code-like chips. The theme now follows the system setting until the user picks one (it was dark by default). |
| App polish | Cards, panels, lists and the top bar use a tone step instead of 1px outlines; real tables and form fields keep theirs. Square corners (radius 3px). Press feedback and transitions on buttons, with a reduced-motion fallback. Nothing under 13px. 44px touch targets on phones. Square badges. "//recent" became "Recent". |
| Login and register | Same shell, a real heading, one archive picture beside the form on wide screens, and the email typed in the home page's closing sentence is carried to the register form. |

## Measured

All with the skill's own tools (`lint.mjs`, `inspect.mjs`), 2026-10-20.

| Check | Before | After |
| --- | --- | --- |
| `inspect.mjs` on the home page at 1440, 768 and 390 px | 13 FAIL, 2 WARN (mono display type, 17 hairlines, no pictures, no focal point, nothing moves, 1.1:1 badge text, text under 13px, headline wrapping to 4 lines on a phone) | **0 FAIL**, 2 WARN: 18 font sizes (they come from the five fluid steps) and no video (the page has one moving photograph, the logbook, drifting slowly) |
| `lint.mjs` on the new public files | 60 FAIL, 36 WARN across `frontend/src` | 0 FAIL, 0 WARN on `HomePage.tsx`, `home/`, `LoginPage.tsx` |
| `lint.mjs` on all of `frontend/src` | 60 FAIL, 36 WARN | 29 FAIL, 13 WARN; what is left is app interface: small section labels, real tables and heatmaps, form field outlines, code in monospace |
| `inspect.mjs` on the login page | not run | 3 FAIL that do not apply to a form page (picture count, focal point, motion); the type, colour, hairline and overflow checks pass |
| Role sweep (Playwright, student, instructor, admin, 8 + 7 + 2 routes each) at 1366 and 390 px, light and dark | passed in step 57 | 4 runs, 0 horizontal overflow, 0 page or console errors |
| `npx tsc --noEmit`, `npm run build`, `npm audit` | pass, 0 | pass, 0 vulnerabilities |

## A bug found and fixed on the way

The first version of the public CSS used global class names (`.statement`, `.row`, `.head`, `.muted`, `.small`, `.wrap`) that the problem page also uses, so the problem statement rendered at display size. Every public rule is now scoped under `.home`. Found by looking at the problem page screenshot, not by the meter.

## Dependency

`@fontsource/bricolage-grotesque` added (self-hosted, no call to a font CDN); `@fontsource/instrument-sans` removed. `npm audit`: 0 vulnerabilities.

## Not done or not measured

- The phone layout of the signed-in top bar still wraps to two rows; the email is hidden to keep it short.
- The Monaco editor still loads from a CDN (known gap).
- No moving clip: no honest footage was searched for; the logbook photograph drifts instead.
- Not browser-tested beyond the sweep: the keyboard path through the live question, and the focus order of the closing sentence form.
- The look is judged from screenshots at three widths in both themes; no user has been shown it.
- The walkthrough video in `docs/demo/` shows the previous look.
