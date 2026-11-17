"""The curated offers Markdown is generated from the browser capture, never typed by hand: the
figures in the file must be the captured ones, and the file must not drift from its capture
(REQ-RAG-01)."""

import importlib.util
import json
from pathlib import Path
from types import ModuleType

import pytest

from app.rag.crawler import CURATED_DIR

pytestmark = pytest.mark.req("REQ-RAG-01")

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "build_curated_offers.py"
CAPTURE = CURATED_DIR / "todas-as-maquininhas.capture.json"
MARKDOWN = CURATED_DIR / "todas-as-maquininhas.md"


def _builder() -> ModuleType:
    spec = importlib.util.spec_from_file_location("build_curated_offers", SCRIPT)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_installments_pair_each_rate_with_its_label() -> None:
    raw = "4,59%Crédito 2x\n   \n   5,71%Crédito 3x\n 6,83%Crédito 4x"
    assert _builder().parse_installments(raw) == [(2, "4,59%"), (3, "5,71%"), (4, "6,83%")]


def test_card_parser_normalises_split_prices_and_collects_features() -> None:
    raw = (
        "Get Lite\nA melhor opção\nR$ 94,80\nR$ 70,80\nà vista\nou:\n12x\nR$\n5\n,90\n"
        "DETALHES DA OFERTA\nPEDIR GET LITE\nAceita Pix\nTela touchscreen\n"
        "Get Smart\nOutra frase\nDe:\nR$ 129,90\nR$\n50\n,00\n/mês\n"
        "DETALHES DA OFERTA\nALUGAR GET SMART\nSimulador de vendas"
    )
    lite, smart = _builder().parse_cards(raw)
    assert lite.name == "Get Lite" and lite.tagline == "A melhor opção"
    assert lite.price == "R$ 94,80 R$ 70,80 à vista ou: 12x R$ 5,90"
    assert lite.features == ["Aceita Pix", "Tela touchscreen"]
    assert smart.price == "De: R$ 129,90 R$ 50,00/mês"
    assert smart.features == ["Simulador de vendas"]


def test_markdown_carries_the_captured_figures() -> None:
    capture = json.loads(CAPTURE.read_text(encoding="utf-8"))
    text = _builder().build(capture)
    for tier in capture["faixas"]:
        assert tier["debito"] in text and tier["credito1x"] in text
        assert f"| {tier['label']} | {tier['debito']} | {tier['credito1x']} |" in text
    assert "valem para a bandeira Visa / Master" in text
    assert "#offers-card" in text


def test_comparison_lists_each_card_without_concluding_what_a_machine_lacks() -> None:
    text = _builder().build(json.loads(CAPTURE.read_text(encoding="utf-8")))
    assert "Get Smart: Aceita Pix, QR Code, aproximação e chip; Wi-fi" in text
    assert "Simulador de vendas" in text and "Tela touchscreen" in text
    # A card that does not list a feature is not proof that the machine lacks it.
    assert "não significa que ela não o tenha" in text
    assert "e não no da" not in text


def test_price_table_puts_every_machine_and_tier_side_by_side() -> None:
    text = _builder().build(json.loads(CAPTURE.read_text(encoding="utf-8")))
    assert "| Faixa de faturamento mensal | Get Lite | Get Clássica | Get Smart |" in text
    # Free from the R$ 20 mil tier (not from R$ 10 mil, where it costs R$ 79,90 a month).
    assert "| Acima de R$ 10 mil | não exibida nesta faixa | R$ 79,90/mês | R$ 129,90/mês |" in text
    assert (
        "| Acima de R$ 20 mil | não exibida nesta faixa | Grátis (valor cheio R$ 79,90) |" in text
    )
    assert "R$ 50,00/mês (valor cheio R$ 129,90)" in text


def test_free_rental_threshold_is_computed_from_the_table() -> None:
    text = _builder().build(json.loads(CAPTURE.read_text(encoding="utf-8")))
    assert "## Quanto preciso faturar por mês para ganhar a maquininha de graça" in text
    classic = "- Get Clássica: aluguel grátis a partir da faixa Acima de R$ 20 mil de faturamento"
    smart = "- Get Smart: aluguel grátis a partir da faixa Acima de R$ 40 mil de faturamento"
    assert classic in text and smart in text
    assert "Acima de R$ 20 mil: R$ 50,00/mês (valor cheio R$ 129,90)" in text


@pytest.mark.parametrize(
    ("tokens", "expected"),
    [
        (["De:", "R$ 79,90", "Grátis"], "Grátis (valor cheio R$ 79,90)"),
        (["Por:", "R$ 79 ,90", "/mês"], "R$ 79,90/mês"),
        (["De:", "R$ 129,90", "R$", "50", ",00", "/mês"], "R$ 50,00/mês (valor cheio R$ 129,90)"),
        (["R$ 94,80", "R$ 70,80", "à vista"], "R$ 94,80 R$ 70,80 à vista"),
    ],
)
def test_display_price_states_what_the_card_shows(tokens: list[str], expected: str) -> None:
    card = _builder().Card(name="Get Clássica", price_tokens=tokens)
    assert card.display_price == expected


def test_markdown_file_is_in_sync_with_the_capture() -> None:
    capture = json.loads(CAPTURE.read_text(encoding="utf-8"))
    expected = _builder().build(capture)
    assert MARKDOWN.read_text(encoding="utf-8").replace("\r\n", "\n") == expected
