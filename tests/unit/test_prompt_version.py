"""Fingerprint estável dos prompts (REQ-OBS-02, ADR 0009)."""

from __future__ import annotations

import pytest

from app.core.prompts import load_prompt, prompt_version


@pytest.mark.req("REQ-OBS-02")
def test_prompt_version_is_12_hex_chars() -> None:
    v = prompt_version("supervisor")
    assert len(v) == 12
    assert all(c in "0123456789abcdef" for c in v)


@pytest.mark.req("REQ-OBS-02")
def test_prompt_version_differs_between_prompts() -> None:
    assert prompt_version("supervisor") != prompt_version("synthesize")


@pytest.mark.req("REQ-OBS-02")
def test_prompt_version_matches_content_hash() -> None:
    import hashlib

    expected = hashlib.sha256(load_prompt("supervisor").encode("utf-8")).hexdigest()[:12]
    assert prompt_version("supervisor") == expected
