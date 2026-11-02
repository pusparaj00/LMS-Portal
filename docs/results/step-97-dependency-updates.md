# Step 97: dependency updates after new advisories (2026-11-02)

The audit of 2026-10-20 found nothing ([dependency-audit-2026-10-20](dependency-audit-2026-10-20.md)). Advisories published since then
were found on 2026-11-02 with `npm audit` in `frontend/` and `pip-audit -r requirements.txt` in the test container (installed into a
temporary directory, not added to the repository).

| Package | Found | Action | Result |
| --- | --- | --- | --- |
| dompurify (through monaco-editor) | 3 advisories, 2 critical, in `<= 3.4.16` | `overrides` raised from 3.4.16 to 3.4.17 | `npm audit`: 0 vulnerabilities |
| vite | 1 moderate, in 6.4.4 | `npm audit fix` (lock file only) | `npm audit`: 0 vulnerabilities |
| pypdf | 14 advisories in 6.20.1 | `requirements.txt` 6.20.1 to 6.21.4 | no longer reported (see test run below) |
| pillow 12.3.0 | 39 advisories, fixed in 13.0.0 | **not changed** | open, below |

## Pillow: why it stays open

Pillow is not in `requirements.txt`; `fastembed==0.9.0` requires it. Pinning `pillow==13.0.0` fails to resolve
(`ResolutionImpossible` while building the test image), so fastembed 0.9.0 does not allow Pillow 13. Moving fastembed to a newer release would
change the embedding library behind note retrieval (TR-V-09, 17 of 20 questions with the right chunk in the top 3), which needs its own
measurement. Our code never imports Pillow (`grep -rli "PIL\|pillow" backend/app backend/evaluation backend/simulation` finds nothing), and
fastembed only uses it for image models, while the project embeds text only. So the advisories are not reachable from the application as
built, but they remain listed by `pip-audit`.

## Tests

`docker compose --profile test run --rm --build test` on the rebuilt image, 2026-11-02: ruff clean, **1171 passed**, 2 warnings, 488.67 s. `pip-audit` afterwards lists only pillow (39 advisories); the 14 pypdf advisories are gone.
