import re
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]

GENERATED = re.compile(
    r"(^|/)(\.env$|\.env\.(?!example$)[^/]+$|[^/]+\.(db|sqlite3?)$|pgdata/|models-cache/"
    r"|evals/reports/|__pycache__/|\.coverage|\.pytest_cache/|\.mypy_cache/|\.ruff_cache/|\.venv/)"
)
SECRET_KEYS = {"OPENAI_API_KEY", "JWT_SECRET", "POSTGRES_PASSWORD", "DATABASE_URL", "REDIS_URL"}


def tracked_files() -> list[str]:
    out = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True)
    if out.returncode != 0:
        # A git worktree mounted in a container points to a host path; the main repository
        # and CI (a normal clone) still run these checks.
        pytest.skip(f"git metadata unavailable here: {out.stderr.strip()[:120]}")
    return out.stdout.splitlines()


@pytest.mark.req("REQ-INF-05")
def test_no_generated_artifacts_tracked() -> None:
    assert [f for f in tracked_files() if GENERATED.search(f)] == []


@pytest.mark.req("REQ-SEC-04")
def test_env_file_is_not_tracked() -> None:
    assert ".env" not in tracked_files()


@pytest.mark.req("REQ-SEC-04")
def test_env_example_has_no_secret_values() -> None:
    values = dict(
        line.split("=", 1)
        for line in (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#")
    )
    assert values.keys() >= SECRET_KEYS
    assert {k: values[k] for k in SECRET_KEYS if values[k].strip()} == {}
