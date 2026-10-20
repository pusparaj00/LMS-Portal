"""TR-O-04: in production mode the API refuses weak or placeholder secrets and never prints them."""
import pytest

from app.config import Settings

STRONG = {
    "app_env": "production",
    "database_url": "postgresql+psycopg://lms_api:" + "d" * 24 + "@db:5432/lms",
    "redis_url": "redis://:" + "r" * 24 + "@redis:6379/0",
    "jwt_secret": "j" * 40,
    "mastery_service_url": "http://mastery:8001",
    "mastery_service_token": "m" * 40,
}


def test_strong_secrets_start():
    Settings(**STRONG).check_production()


def test_development_accepts_short_secrets():
    Settings(**{**STRONG, "app_env": "development", "jwt_secret": "x"}).check_production()


@pytest.mark.parametrize(
    "field,value",
    [
        ("jwt_secret", "j" * 31),
        ("jwt_secret", "change-me-" + "j" * 30),
        ("mastery_service_token", "short"),
        ("database_url", "postgresql+psycopg://lms_api:short@db:5432/lms"),
        ("database_url", "postgresql+psycopg://lms_api@db:5432/lms"),
        ("redis_url", "redis://:" + "Password" + "1" * 16 + "@redis:6379/0"),
        ("redis_url", "redis://redis:6379/0"),
    ],
)
def test_weak_secret_stops_startup_without_printing_it(field, value):
    with pytest.raises(RuntimeError) as caught:
        Settings(**{**STRONG, field: value}).check_production()
    message = str(caught.value)
    assert "refuses weak secrets" in message
    assert value not in message


def test_the_api_process_refuses_to_start_with_a_weak_secret_in_production():
    """Checked at import, not at the first request: a weak secret must stop the container, not just fail its health check."""
    import os
    import subprocess
    import sys

    weak = "weak-" + "w" * 3
    result = subprocess.run(
        [sys.executable, "-c", "import app.main"],
        env={**os.environ, "APP_ENV": "production", "JWT_SECRET": weak},
        capture_output=True, text=True, timeout=120, cwd=os.path.dirname(os.path.dirname(__file__)),
    )
    assert result.returncode != 0
    assert "refuses weak secrets" in result.stderr
    assert weak not in result.stderr
