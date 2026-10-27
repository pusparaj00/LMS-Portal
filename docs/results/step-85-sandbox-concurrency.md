# Step 85: the sandbox runs four jobs at a time (TR-P-04, TR-P-05, TR-X-01 to TR-X-06)

Date: 2026-10-27. Before this step the runner took one job at a time; step 80 measured 7 of 30 students refused with "sandbox is
busy" when all 30 started together.

## What changed

| Change | Where |
| --- | --- |
| `SANDBOX_WORKERS` (default 4) worker processes each claim the oldest job with an atomic rename out of `in/` into a root-only `claimed/` directory; the supervisor restarts a worker that dies | `sandbox/supervisor.py` |
| One uid per worker (10002 to 10005): a worker's run directory is private to its uid, the process limit counts only its own processes, and ending a run kills only that uid's processes. With one shared uid, one run's clean-up would have killed the others and every run could have read every other run's code. | same |
| Container limits sized for four runs at 256 MiB of address space each: memory 512 MiB to 1536 MiB, CPUs 1.0 to 4.0 | `docker-compose.yml` |
| The runner reports `run_uids` and `workers` in `config.json` | `supervisor.py`, `test_sandbox_config.py` |
| The API's queue limit (20 waiting jobs, 3 s wait) is unchanged and now counts waiting jobs only | `backend/app/sandbox.py` |

## Tests (`backend/tests/test_sandbox_adversarial.py`)

- A job running beside another cannot read its working directory or environment or signal it (the probe found the other
  job's process and was refused 3 of 3 times; the other job finished normally).
- Ending a run that spins at the CPU limit does not kill a run beside it.
- Four jobs that each sleep 2 s finish together in under 5 s (one after another would take 8 s or more).
- A student cannot list the `claimed` directory. All 13 earlier attacks still contained.
- Full suite: 1156 passed, `ruff` clean (`docker compose --profile test run --rm --build test sh -c "ruff check . && pytest -q"`).

## Measured

`python -m evaluation.load concurrent 30` on the production configuration (`compose.prod.yml`, throwaway project, live
Gemini), the same command and host as step 80:

| | Failed steps | Flows with no failed step | Wall time for all 30 |
| --- | --- | --- | --- |
| Before (step 80, one job at a time) | 7 flows refused with "sandbox busy" | 23 of 30 | 44.4 s |
| After, run 1 | 0 of 690 | 30 of 30 | 26.0 s |
| After, run 2 | 0 of 690 | 30 of 30 | 15.6 s |

The wall time includes live model calls, which vary from run to run. The first run after the change printed nothing (my output
filter), so it is not counted; a later run failed at registration with HTTP 429 because the per-address registration limit
(TR-S-04) was used up by the repeated runs, which is unrelated to the sandbox. The sandbox container used at most 36 MiB
during the load.

Storm test (`16 attacks at once`: four memory bombs, four fork bombs, four CPU spins, four output floods, started together
through `run_batch`): all 16 contained in 23.2 s (memory_limit 4, time_limit 8, output_limit 4); the container was not
OOM-killed, had 0 restarts, stayed healthy, and answered a normal job afterwards.

## Risks

- The host now allows the sandbox four CPUs and 1.5 GiB when needed; on a small server these caps need to be reconsidered.
- A bigger class than about 30 submitting in the same second can still see "sandbox busy" (the queue allows 20 waiting).
- Isolation between concurrent runs rests on separate uids and a private directory; there is no per-run network or
  filesystem namespace. The earlier single-run attacks are still contained, and the new tests cover the cross-run cases above.
