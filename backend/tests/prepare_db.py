"""Creates and migrates the database the tests run against (TR-A-01, TR-V-10).

The tests create and delete users, courses and mastery rows by the thousand, and some wipe the synthetic demo class, so
they never run against the app's own database. They use `lms_test` on the same Postgres server. This script refuses
to touch any other database.

    python -m tests.prepare_db           create it if missing, then bring it up to date
    python -m tests.prepare_db --reset   drop it and start again from nothing
"""
import os
import subprocess
import sys

import redis
from sqlalchemy import create_engine, text
from sqlalchemy.engine import make_url

TEST_DATABASE = "lms_test"


def clear_cache() -> None:
    """A new database numbers its rows from 1 again, so cached explanations, probe offers and hint counters from the
    old one (stored in Redis by submission, problem and user id) would be taken for the new rows' own."""
    url = os.environ["REDIS_URL"]
    if not url.endswith("/1"):
        sys.exit("refusing to clear Redis: the tests' database is number 1, and this URL is not")
    redis.Redis.from_url(url).flushdb()
    print("cleared the tests' Redis database")


def main() -> None:
    owner = make_url(os.environ["OWNER_DATABASE_URL"])
    if owner.database != TEST_DATABASE:
        sys.exit(f"refusing to prepare '{owner.database}': the test database must be named {TEST_DATABASE}")
    admin = create_engine(owner.set(database="postgres"), isolation_level="AUTOCOMMIT")
    with admin.connect() as conn:
        if "--reset" in sys.argv:
            conn.execute(text(f"DROP DATABASE IF EXISTS {TEST_DATABASE} WITH (FORCE)"))
        exists = conn.execute(text("SELECT 1 FROM pg_database WHERE datname = :d"), {"d": TEST_DATABASE}).first()
        if not exists:
            conn.execute(text(f"CREATE DATABASE {TEST_DATABASE}"))
            print(f"created database {TEST_DATABASE}")
            clear_cache()
    subprocess.run(["alembic", "upgrade", "head"], check=True)


if __name__ == "__main__":
    main()
