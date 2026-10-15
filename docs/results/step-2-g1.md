# Step 2 results (gate G1)

Run on 2026-10-15 on Docker Desktop (WSL2). Command for the test results:
`docker compose --profile test run --rm test` (ruff, then 73 pytest tests, 40.11 s).

## Adversarial suite (TR-V-01)

Every program ran inside the sandbox container (`backend/tests/test_sandbox_adversarial.py`).
After the attacks the host checks passed: `/etc/pwned` and `/tmp/pwned` do not exist, only one
student-uid process exists (the checker itself) and the sandbox still answers.

| Attack | Contained result | Runtime ms |
| --- | --- | --- |
| infinite loop | time_limit | 2073 |
| sleep past wall clock | time_limit | 4232 |
| memory bomb (one allocation) | memory_limit | 34 |
| memory bomb (growing list) | memory_limit (time_limit in 1 of 10 runs) | 519 |
| fork bomb | time_limit | 4510 |
| network call | runtime_error (network unreachable) | 116 |
| network call to loopback service | runtime_error (connection refused) | 116 |
| symlink to a host path | runtime_error (permission denied) | 18 |
| list the job directories | runtime_error (permission denied) | 19 |
| write outside the temp directory | runtime_error (read-only file system) | 17 |
| write into the results directory | runtime_error (permission denied) | 18 |
| very large output | output_limit | 19 |
| shell characters in input | ok, echoed literally | 18 |

## Sandbox configuration (TR-X-02, TR-X-04 to TR-X-06)

`docker inspect lms-sandbox-1`: NetworkMode=none, ReadonlyRootfs=true, CapDrop=ALL,
CapAdd=CHOWN DAC_OVERRIDE KILL SETGID SETUID, no-new-privileges, PidsLimit=256,
Memory=512 MiB, 1 CPU, init=true, no published ports.

Limits reported by the runner itself (`/jobs/config.json`): CPU 2 s, wall 4 s (raised to 10 s in Step 3, see below), memory 256 MiB,
16 processes, 32 open files, 1 MiB per output file, 64 KiB returned text, 256 KiB code,
64 KiB stdin per run, 60 runs per job. Network interfaces: `lo` only. Student uid 10002 with
an empty capability set.

## Question bank (TR-D-04)

`docker compose exec api python -m app.bank_import data/bank --dry-run`:
validated 47 of 47 (35 coding problems, 12 tracing items). The validator rejected one of my
own tracing items on the first run (its code raised a TypeError); it was fixed and re-run.
Every problem is marked "needs human review".

## Browser check (F-10)

Headless Chromium drove the real UI: register, enrol, open "Sum of two numbers", submit.
Correct code: Accepted, 5 of 5 tests. Wrong code: 2 of 5 failed in categories basic and
negative_numbers. An infinite loop on Run: "Your code ran too long." (4170 ms).

## Fixes after review (2026-10-15)

- The runner crashed with `FileNotFoundError` when the API withdrew a queued job between the
  directory scan and `stat()`. Reproduced once in 3 runs of
  `test_sandbox_survives_jobs_withdrawn_while_queued` against the old runner; 0 crashes in 5
  runs after the fix. All services now restart on failure.
- The earlier unexplained flake was the growing-list memory bomb ending as `time_limit`
  (CPU limit reached before the memory limit). Both outcomes are contained; the test accepts
  either for that one attack. Full suite after the fixes: 74 passed, three runs in a row.

## Change in Step 3 (2026-10-15)

The wall-clock limit was raised from 4 s to 10 s (the TR-P-01 hard stop). In a fresh-clone run on a loaded machine
(245 s for a suite that normally takes 70 s) a trivial `print('alive')` hit the 4 s limit. CPU time is still limited to
2 s, so an infinite loop is stopped after about 2 s; only sleeping programs and the fork bomb now take about 10 s.
