from pathlib import Path

import pytest
from pydantic import ValidationError

from app.core.config import Settings

ROOT = Path(__file__).resolve().parents[2]


def _env_example() -> dict[str, str]:
    lines = (ROOT / ".env.example").read_text(encoding="utf-8").splitlines()
    return dict(line.split("=", 1) for line in lines if line and not line.startswith("#"))


@pytest.mark.req("REQ-SEC-01")
def test_settings_load_from_environment(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("MAX_STEPS", "4")
    settings = Settings(_env_file=None)
    assert settings.max_steps == 4
    assert settings.jwt_secret.get_secret_value()


@pytest.mark.req("REQ-SEC-01")
def test_short_jwt_secret_fails_at_startup(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("JWT_SECRET", "too-short")
    with pytest.raises(ValidationError, match="32 bytes"):
        Settings(_env_file=None)


@pytest.mark.req("REQ-ORC-04")
def test_numeric_defaults_match_env_example(monkeypatch: pytest.MonkeyPatch) -> None:
    example = _env_example()
    numeric = {k: v for k, v in example.items() if v and v.replace(".", "", 1).isdigit()}
    for key in numeric:
        monkeypatch.delenv(key, raising=False)
    settings = Settings(_env_file=None)
    for key, value in numeric.items():
        assert float(getattr(settings, key.lower())) == float(value), key
