import pytest
from app.rag.chunking import MAX_TOKENS, MIN_TOKENS, OVERLAP_TOKENS, chunk_text, count_tokens
from app.rag.crawler import extract

from tests.fixtures.site import BASE, FIXTURES

pytestmark = pytest.mark.req("REQ-RAG-03")


def _words(prefix: str, n: int) -> str:
    return " ".join(f"{prefix}{i}" for i in range(n))


def test_limits_match_the_plan() -> None:
    assert (MIN_TOKENS, MAX_TOKENS, OVERLAP_TOKENS) == (400, 800, 80)


def test_splits_by_headings_with_section_path() -> None:
    text = "# A\n\npara a\n\n## B\n\npara b\n\n### C\n\npara c\n\n## D\n\npara d"
    chunks = chunk_text(text, title="Doc")
    assert [(c.section, c.content) for c in chunks] == [
        ("A", "para a"),
        ("A > B", "para b"),
        ("A > B > C", "para c"),
        ("A > D", "para d"),
    ]


def test_text_without_headings_uses_the_title() -> None:
    chunks = chunk_text("primeira linha\n\nsegunda linha", title="Guia PDF")
    assert [(c.section, c.content) for c in chunks] == [
        ("Guia PDF", "primeira linha\n\nsegunda linha")
    ]


def test_empty_text_has_no_chunks() -> None:
    assert chunk_text("  \n\n ", title="x") == []


@pytest.mark.parametrize(
    "body",
    [
        _words("w", 2000),  # one huge paragraph
        "\n\n".join(_words(f"p{j}x", 50) for j in range(30)),  # many small paragraphs
    ],
    ids=["long-paragraph", "many-paragraphs"],
)
def test_long_sections_are_400_to_800_tokens_with_overlap_80(body: str) -> None:
    chunks = chunk_text(f"# Seção\n\n{body}", title="Doc")
    assert len(chunks) >= 2
    sizes = [count_tokens(c.content) for c in chunks]
    assert all(s <= MAX_TOKENS for s in sizes), sizes
    assert all(s >= MIN_TOKENS for s in sizes[:-1]), sizes
    for prev, nxt in zip(chunks, chunks[1:], strict=False):
        assert prev.content.split()[-OVERLAP_TOKENS:] == nxt.content.split()[:OVERLAP_TOKENS]
    # Nothing is lost: every word of the section appears in some chunk.
    assert set(body.split()) <= {w for c in chunks for w in c.content.split()}


def _table(rows: int) -> str:
    lines = ["| Plano | Débito | Crédito |", "|---|---|---|"]
    lines += [f"| Plano {i} | {i},99% | {i},49% |" for i in range(rows)]
    return "\n".join(lines)


@pytest.mark.parametrize("rows", [20, 200], ids=["small-table", "table-over-max"])
def test_table_is_never_split(rows: int) -> None:
    table = _table(rows)
    text = f"# Tarifas\n\n{_words('a', 700)}\n\n{table}\n\n{_words('b', 300)}"
    chunks = chunk_text(text, title="Doc")
    with_table = [c for c in chunks if "| Plano" in c.content]
    assert len(with_table) == 1
    assert table in with_table[0].content


def test_fixture_comparison_table_stays_whole() -> None:
    page = extract(
        f"{BASE}/maquininhas/", (FIXTURES / "maquininhas.html").read_bytes(), "text/html"
    )
    assert page is not None
    chunks = chunk_text(page.text, title=page.title)
    table_chunks = [c for c in chunks if "| Recurso |" in c.content]
    assert len(table_chunks) == 1
    assert table_chunks[0].section == "Maquininhas Getnet > Comparativo"
    for row in (
        "| Tela |",
        "| Conexão |",
        "| Pix na máquina |",
        "| Aplicativos |",
        "| Impressora |",
    ):
        assert row in table_chunks[0].content
