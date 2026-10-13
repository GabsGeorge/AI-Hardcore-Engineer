import pytest

from app.rag.retriever import Bm25Index, tokenize

pytestmark = pytest.mark.req("REQ-RAG-04")


def test_tokenize_lowercases_strips_accents_and_stopwords() -> None:
    assert tokenize("A Antecipação de recebíveis e o PIX da Get Smart!") == [
        "antecipacao",
        "recebiveis",
        "pix",
        "get",
        "smart",
    ]
    assert tokenize("What is the fee for the Payment Link?") == ["what", "fee", "payment", "link"]


def test_tokenize_keeps_codes_and_has_no_stemming() -> None:
    assert tokenize("Código 51: maquininhas") == ["codigo", "51", "maquininhas"]


ROWS = [
    (10, "pt", "A Get Smart tem tela touch, Wi-Fi e chip 4G."),
    (20, "pt", "Código de recusa 51: saldo insuficiente no cartão."),
    (30, "pt", "A Get Clássica tem teclado físico e impressora."),
    (40, "en", "Receivables advance lets merchants get paid earlier."),
]


def test_bm25_finds_exact_terms() -> None:
    index = Bm25Index(ROWS)
    assert index.search("Get Smart", k=20)[0] == 10
    assert index.search("o que significa o código 51?", k=20)[0] == 20
    assert index.search("advance", k=20) == [40]


def test_bm25_returns_only_matches_and_respects_k_and_lang() -> None:
    index = Bm25Index(ROWS)
    assert index.search("zebra inexistente", k=20) == []
    assert index.search("de o a", k=20) == []  # only stopwords
    assert len(index.search("get", k=1)) == 1
    assert set(index.search("get", k=20)) == {10, 30, 40}
    assert index.search("get", k=20, lang="en") == [40]


def test_bm25_over_an_empty_corpus() -> None:
    assert Bm25Index([]).search("get smart", k=20) == []
