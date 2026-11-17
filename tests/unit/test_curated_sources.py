"""Curated sources: content of pages that the site builds with JavaScript, captured with a browser
and ingested like any other page (REQ-RAG-01). It may only cite an allowed domain, and its file has
to stay inside the curated directory."""

from pathlib import Path

import pytest

from app.rag.chunking import chunk_text
from app.rag.crawler import CURATED_DIR, CuratedSource, Sources, load_curated, load_sources

pytestmark = pytest.mark.req("REQ-RAG-01")

URL = "https://site.getnet.com.br/todas-as-maquininhas/#offers-card"


def _sources(*items: CuratedSource) -> Sources:
    return Sources(allowed_domains=["getnet.com.br"], curated=list(items))


def test_curated_page_is_loaded_from_its_file(tmp_path: Path) -> None:
    (tmp_path / "taxas.md").write_text("# Taxas\n\n## Débito\n\n0,85%\n", encoding="utf-8")
    pages = load_curated(
        _sources(CuratedSource(path="taxas.md", url=URL, title="Taxas", lang="pt")), tmp_path
    )
    assert len(pages) == 1
    assert pages[0].url == URL and pages[0].title == "Taxas" and pages[0].lang == "pt"
    assert pages[0].source_type == "page" and "0,85%" in pages[0].text


def test_curated_url_outside_the_allowlist_is_rejected(tmp_path: Path) -> None:
    (tmp_path / "x.md").write_text("# X\n", encoding="utf-8")
    with pytest.raises(ValueError, match="allowlist"):
        load_curated(
            _sources(CuratedSource(path="x.md", url="https://evil.example/x", title="X")), tmp_path
        )


def test_curated_url_must_be_https(tmp_path: Path) -> None:
    (tmp_path / "x.md").write_text("# X\n", encoding="utf-8")
    with pytest.raises(ValueError, match="allowlist"):
        load_curated(
            _sources(CuratedSource(path="x.md", url="http://site.getnet.com.br/x", title="X")),
            tmp_path,
        )


def test_curated_path_cannot_escape_the_directory(tmp_path: Path) -> None:
    base = tmp_path / "curated"
    base.mkdir()
    (tmp_path / "secret.md").write_text("# segredo\n", encoding="utf-8")
    with pytest.raises(ValueError, match="escapes"):
        load_curated(
            _sources(CuratedSource(path="../secret.md", url=URL, title="X")),
            base,
        )


def test_shipped_sources_list_the_captured_offers_page() -> None:
    sources = load_sources()
    item = next(c for c in sources.curated if c.url == URL)
    assert (CURATED_DIR / item.path).is_file()
    [page] = [p for p in load_curated(sources) if p.url == URL]
    assert "Get Smart" in page.text and "Get Clássica" in page.text


def test_captured_offers_split_into_self_contained_chunks() -> None:
    [page] = [p for p in load_curated(load_sources()) if p.url == URL]
    chunks = chunk_text(page.text, page.title)
    by_section = {c.section: c.content for c in chunks}
    # One section per revenue tier, and the comparison of the two machines is its own chunk.
    tier = next(s for s in by_section if "Acima de R$ 80 mil" in s and "Taxas na faixa" in s)
    assert "Débito: 0,85%" in by_section[tier] and "Crédito 12x: 15,79%" in by_section[tier]
    comparison = next(s for s in by_section if "o que cada cartão lista" in s)
    assert "Simulador de vendas" in by_section[comparison]
