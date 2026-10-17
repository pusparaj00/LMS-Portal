"""Agree to the privacy notice for a student the scripts just registered (TR-S-05).

The evaluation and load scripts act as students, and a student's code, answers and messages are only processed after they
have agreed. These accounts are synthetic test accounts made by the scripts, so the agreement is recorded as such.
"""


def agree(client, api: str, headers: dict) -> None:
    """`client` is an httpx.Client or a FastAPI TestClient; `api` is the API prefix."""
    version = client.get(f"{api}/consent/notice", headers=headers).json()["version"]
    reply = client.post(f"{api}/consent/accept", headers=headers, json={"version": version, "adult": True})
    if reply.status_code != 200:
        raise RuntimeError(f"could not record consent: {reply.status_code} {reply.text[:100]}")
