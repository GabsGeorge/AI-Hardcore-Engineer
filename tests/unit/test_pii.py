import pytest

from app.guardrails.pii import mask

pytestmark = pytest.mark.req("REQ-GR-02")


@pytest.mark.parametrize(
    ("text", "kind", "token"),
    [
        ("meu cpf é 529.982.247-25", "cpf", "[CPF]"),
        ("cpf 52998224725 ok", "cpf", "[CPF]"),
        ("cnpj 11.222.333/0001-81", "cnpj", "[CNPJ]"),
        ("cartão 4111 1111 1111 1111", "card", "[CARTAO]"),
        ("cartão 5555-5555-5555-4444", "card", "[CARTAO]"),
        ("email fulano.silva@example.com", "email", "[EMAIL]"),
        ("ligue (51) 99876-5432", "phone", "[TELEFONE]"),
        ("ligue +55 51 99876-5432", "phone", "[TELEFONE]"),
    ],
)
def test_masks_valid_pii(text: str, kind: str, token: str) -> None:
    masked, found = mask(text)
    assert token in masked
    assert kind in found


@pytest.mark.parametrize(
    "text",
    [
        "cpf inválido 529.982.247-26",
        "cnpj inválido 11.222.333/0001-82",
        "cartão inválido 4111 1111 1111 1112",
        "vendi R$ 1500 ontem em 3 parcelas",
        "código de recusa 51 na transação tx-2024",
    ],
)
def test_does_not_mask_values_that_fail_validation(text: str) -> None:
    masked, found = mask(text)
    assert masked == text
    assert found == []


def test_masks_multiple_items_and_reports_each_type_once() -> None:
    masked, found = mask("cpf 529.982.247-25, cartão 4111111111111111, cpf 52998224725")
    assert "529.982" not in masked and "4111" not in masked
    assert sorted(found) == ["card", "cpf"]
