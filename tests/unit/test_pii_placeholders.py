"""Fictitious CPF/CNPJ that people type as placeholders must be masked even though their check
digits are wrong; arbitrary numbers that merely fail validation must survive (test_pii.py)."""

import pytest

from app.guardrails.pii import mask

pytestmark = pytest.mark.req("REQ-GR-02")


@pytest.mark.parametrize(
    ("text", "tag"),
    [
        ("Meu CPF é 123.456.789-00, qual é o próximo passo?", "[CPF]"),
        ("cpf 111.111.111-11", "[CPF]"),
        ("cpf 000.000.000-00", "[CPF]"),
        ("cnpj 11.111.111/1111-11", "[CNPJ]"),
    ],
)
def test_placeholder_documents_are_masked(text: str, tag: str) -> None:
    masked, found = mask(text)
    assert tag in masked
    assert found


@pytest.mark.parametrize(
    "text",
    ["cpf inválido 529.982.247-26", "cnpj inválido 11.222.333/0001-82"],
)
def test_ordinary_invalid_numbers_are_not_masked(text: str) -> None:
    masked, found = mask(text)
    assert masked == text
    assert not found
