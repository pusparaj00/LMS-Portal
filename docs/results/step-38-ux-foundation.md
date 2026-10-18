# Step 38: UX foundation (F-01, F-34, F-60, TR-P-09)

Date: 2026-10-18. Branch `step-38-ux-foundation`. Companion: `docs/ux-plan.md` sections 1, 3, 4.0 and 5.

## Decision recorded first

`docs/architecture.md` was compared with the built system before this step. The backend honours its seven rules but is
not identical to the document. The user accepted the differences and asked for the UX slice to go ahead.

| Area | architecture.md | Built |
| --- | --- | --- |
| Mastery service | in-process module with its own pool | separate container with its own token |
| Database roles | `app_ro_rw`, `mastery_writer`, `app_ro` | `lms_api`, `lms_mastery`, `lms_chat` |
| Ledger key | `evidence_type` + `evidence_id`, unique | `evidence_type` + `submission_id` + `evidence_ref` (uniqueness not checked in this step) |
| Sandbox | separate zone over HTTP | same host, file jobs on a volume, no port, no Docker socket |
| Layout | `app/{api,auth,router,...}`, `sim/` | flat `app/` with `routers/` and `services/`, `backend/simulation/` |
| Beyond the document | not described | LTI 1.3, erasure, audit trail, consent, gradebook, announcements, accounts |

## What changed

| Item | Requirement | Change |
| --- | --- | --- |
| Tokens | TR-P-09, ux-plan 1.1 | Dark is the default, light is a toggle stored in the browser. The existing variable names stay, so every page took the new colours. Five-step mastery ramp added. |
| Fonts | ux-plan 1.2, 4.0 rule 4 | `@fontsource/instrument-sans` and `@fontsource/jetbrains-mono`, Latin subset only, bundled with the app (no remote font request). |
| `MasteryStrip`, `DeltaChip` | F-34, F-60 | Value, label and change chip. `MasteryBars` now renders strips, so the dashboard, placement result and teacher view use it. |
| `EvidenceChip`, `ActivityLog`, `TerminalWindow` | ux-plan 5 | New components, used by the home page. The activity log is not yet wired to live submissions (next slice). |
| Public home page (`#/`) | F-01, ux-plan 4.0 | Log in top-left, hero replay with Pause, Replay and a text version, feature list with preview, walkthrough tabs, comparison, roles, limits, courses, status table, build log, FAQ, footer. All sample data is labelled. |
| Login and register | F-01 | Public layout, back link to the home page. A signed-out deep link shows the login form and returns to that page after sign-in. |
| Signed-in shell | TR-P-09, ux-plan 3 | Theme toggle and Menu button in the top bar, menu closed by default on a problem page, `//recent` list of opened problems (cleared at logout), signed-in view of the home page at `#/home` with Open dashboard. |

Status table and build log on the home page mirror `docs/results/gap-report.md`. Three statements in the plan's starting
copy were left out or changed because the product does not do them: an "instructor can allow the full solution" hint
level, an admin audit viewer, and an evidence count on the strip (the API has no `n_events`).

## Measured (all on 2026-10-18, against a throwaway `docker compose -p lmsui` stack, never the restored database)

| Check | Command or method | Result |
| --- | --- | --- |
| Type check | `npm run lint` | clean |
| Build | `npm run build` | JS 354.31 kB (105.59 kB gzip), CSS 28.20 kB (6.61 kB gzip) |
| Dependency audit | `npm audit` | 0 vulnerabilities |
| Backend suite | `docker compose --profile test run --rm test` | ruff clean, 672 passed in 204.63 s (unchanged: this step touches no backend code) |
| Contrast, both themes | computed from the real tokens (WCAG formula), 17 text pairs and 5 ramp fills per theme | First run: 4 light-theme failures (pass text 4.30, three ramp fills 1.59 to 2.16 against the track). Tokens darkened. Second run: all pass; lowest text ratio 4.53, lowest ramp ratio 3.30. |
| Behaviour (Playwright, Chromium) | scripted | 13 of 13 pass: tab order skip link then Log in; Log in at x=20 y=10; no request to another origin from the home page; dark default; theme survives reload; reduced motion shows the final replay frame; deep link returns after login; menu closed on a problem page; Menu opens it; `//recent` lists the problem; Open dashboard for a signed-in visitor; logout clears the list |
| Horizontal overflow | 11 signed-in pages and the home page, 1366 px and 390 px | 0 px everywhere (the signed-in header overflowed by 140 to 159 px at 390 px until it was allowed to wrap) |
| Placement test end to end | scripted student, 10 answers including the two coding items | completed; result page shows 12 strips; no page errors |

## Not done, open

- **The problem page loads the code editor from `cdn.jsdelivr.net`.** This predates the step and breaks the plan's
  offline demo. The editor package is already a dependency, so bundling it is a small change, but it is outside this slice.
- Not built: the problem workspace and assistant dock layout, command palette, Changes tab, `/s` `/i` `/a` routes
  (the hash routes stay because the LTI landing and several tests use them), the evidence count on the strip, and the
  contrast check of the instructor heatmap cells (they keep their own colours).
- The home page has no dated build log: the documents do not give a date for each gate.
- No second person has looked at the design. The plan's hallway test and greyscale check are not run.
- Log in is the second tab stop, after the skip link, which the plan also asks for first; the skip link comes first
  because it exists to be first.
