"""TR-X-02, TR-X-04, TR-X-05, TR-X-07: the runner reports its own effective settings."""
import json
import os
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def config():
    return json.loads((Path(os.environ["JOBS_DIR"]) / "config.json").read_text())


def test_runner_has_no_network_and_a_read_only_root(config):
    assert config["network_interfaces"] == ["lo"]
    assert config["root_filesystem_writable"] is False


def test_runner_reports_every_explicit_limit(config):
    assert set(config["limits"]) == {
        "cpu_seconds", "wall_seconds", "compile_wall_seconds", "memory_bytes", "max_processes", "max_open_files",
        "output_file_bytes", "result_text_bytes", "max_code_bytes", "max_stdin_bytes",
        "max_runs_per_job",
    }
    assert all(isinstance(v, int) and v > 0 for v in config["limits"].values())
    assert config["limits"]["wall_seconds"] > config["limits"]["cpu_seconds"]


def test_student_code_runs_as_an_unprivileged_uid(config):
    assert config["run_uid"] == 10002


def test_the_sandbox_has_no_listening_interface():
    # Jobs travel only through the shared volume, so the API holds no sandbox URL or token.
    assert "SANDBOX_URL" not in os.environ


def test_runner_reports_per_language_run_and_compile_profiles(config):
    assert set(config["profiles"]["run"]) == {"python", "java", "c"}
    assert set(config["profiles"]["compile"]) == {"java", "c"}
    assert "javac" in config["java"] or "openjdk" in config["java"]
    assert config["cc"]
