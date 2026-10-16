"""What the audit trail shows for a time window (TR-S-08), for step 2 of docs/breach-procedure.md.

It lists the signs of a breach (password guessing, one account reading many records that are not its own, exports,
new staff accounts) and the students whose data may be affected, as the facts a notice to the regulator needs.

Usage: python -m app.breach_report --since 2026-10-16T00:00 [--until 2026-10-17T00:00]
"""
import argparse
import json
import re
from datetime import UTC, datetime

from sqlalchemy import Connection, text

from app.db import get_engine

FAILED_LOGINS_PER_IP = 10
FAILED_LOGINS_PER_ACCOUNT = 5
REFUSED_READS_PER_USER = 10
SUBMISSION_PATH = re.compile(r"^/api/v1/submissions/(\d+)")


def _rows(conn: Connection, sql: str, window: dict) -> list[dict]:
    return [dict(r) for r in conn.execute(text(sql), window).mappings()]


def report(conn: Connection, since: datetime, until: datetime) -> dict:
    window = {"since": since, "until": until}
    in_window = "at >= :since AND at < :until"
    failed_by_ip = _rows(conn, (
        f"SELECT ip, count(*) AS failures, count(DISTINCT detail->>'email_tag') AS accounts_tried, min(at) AS first,"
        f" max(at) AS last FROM audit_events WHERE event = 'auth.login_failed' AND {in_window}"
        f" GROUP BY ip HAVING count(*) >= {FAILED_LOGINS_PER_IP} ORDER BY failures DESC"
    ), window)
    failed_by_account = _rows(conn, (
        f"SELECT detail->>'email_tag' AS email_tag, user_id, count(*) AS failures, count(DISTINCT ip) AS addresses"
        f" FROM audit_events WHERE event = 'auth.login_failed' AND {in_window}"
        f" GROUP BY 1, 2 HAVING count(*) >= {FAILED_LOGINS_PER_ACCOUNT} ORDER BY failures DESC"
    ), window)
    # an account that later logged in from an address that guessed passwords may have been taken over
    logins_after_guessing = _rows(conn, (
        f"SELECT ok.user_id, ok.ip, ok.at FROM audit_events ok WHERE ok.event = 'auth.login' AND ok.{in_window}"
        f" AND ok.ip IN (SELECT ip FROM audit_events WHERE event = 'auth.login_failed' AND {in_window}"
        f" GROUP BY ip HAVING count(*) >= {FAILED_LOGINS_PER_IP}) ORDER BY ok.at"
    ), window)
    refused = _rows(conn, (
        f"SELECT user_id, count(*) AS refused, count(*) FILTER (WHERE event = 'access.not_found') AS not_found,"
        f" array_agg(DISTINCT ip) AS addresses, array_agg(detail->>'path' ORDER BY at) AS paths"
        f" FROM audit_events WHERE event IN ('access.denied', 'access.not_found') AND user_id IS NOT NULL"
        f" AND {in_window} GROUP BY user_id HAVING count(*) >= {REFUSED_READS_PER_USER} ORDER BY refused DESC"
    ), window)
    exports = _rows(conn, (
        f"SELECT at, user_id, ip, (detail->>'course_id')::int AS course_id, detail->>'kind' AS kind"
        f" FROM audit_events WHERE event = 'export.download' AND {in_window} ORDER BY at"
    ), window)
    staff = _rows(conn, (
        f"SELECT at, user_id, detail->>'role' AS role FROM audit_events WHERE event = 'staff.created'"
        f" AND {in_window} ORDER BY at"
    ), window)
    erasures = _rows(conn, (
        f"SELECT event, count(*) AS events FROM audit_events WHERE event LIKE 'erasure.%' AND {in_window}"
        f" GROUP BY event ORDER BY event"
    ), window)

    # Whose records the refused reads were aimed at, and which students' data left in an export.
    probed = sorted({int(m.group(1)) for r in refused for p in r["paths"] if (m := SUBMISSION_PATH.match(p or ""))})
    owners = conn.execute(
        text("SELECT DISTINCT user_id FROM submissions WHERE id = ANY(:ids)"), {"ids": probed}
    ).scalars().all()
    exported = conn.execute(
        text("SELECT DISTINCT user_id FROM enrollments WHERE course_id = ANY(:ids)"),
        {"ids": [e["course_id"] for e in exports]},
    ).scalars().all()
    for r in refused:
        r["paths"] = r["paths"][:20]  # the first ones are enough to see the pattern
    return {
        "window": {"since": since.isoformat(), "until": until.isoformat()},
        "password_guessing_by_address": failed_by_ip,
        "password_guessing_by_account": failed_by_account,
        "logins_from_guessing_addresses": logins_after_guessing,
        "accounts_with_many_refused_reads": refused,
        "exports": exports,
        "staff_accounts_created": staff,
        "erasures": erasures,
        "possibly_affected_students": {
            "owners_of_probed_submissions": sorted(owners),
            "students_in_exported_courses": sorted(exported),
        },
        "note": "Probed records were refused, not read; check the request log for any 200 on the same paths.",
    }


def _when(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--since", type=_when, required=True, help="ISO time, UTC if no zone is given")
    parser.add_argument("--until", type=_when, default=datetime.now(UTC))
    args = parser.parse_args()
    with get_engine().connect() as conn:
        print(json.dumps(report(conn, args.since, args.until), indent=2, default=str))


if __name__ == "__main__":
    main()
