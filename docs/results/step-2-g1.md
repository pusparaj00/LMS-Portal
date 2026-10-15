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
| memory bomb (growing list) | memory_limit | 519 |
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

Limits reported by the runner itself (`/jobs/config.json`): CPU 2 s, wall 4 s, memory 256 MiB,
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
