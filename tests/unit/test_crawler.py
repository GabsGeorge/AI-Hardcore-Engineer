import httpx
import pytest
from app.rag.crawler import Crawler, Seed, SitemapSource, Sources, extract, is_allowed, load_sources

from tests.fixtures.site import BASE, FIXTURES, OUTSIDE, FakeSite

pytestmark = pytest.mark.req("REQ-RAG-01")

SOURCES = Sources(
    allowed_domains=["getnet.com.br"],
    seeds=[
        Seed(url=f"{BASE}/maquininhas/"),
        Seed(url=f"{BASE}/docs/guia-crediario.pdf", type="pdf"),
        Seed(url=OUTSIDE),
        Seed(url=f"{BASE}/antigo/"),
    ],
    sitemaps=[SitemapSource(url=f"{BASE}/sitemap.xml")],
    max_pages=20,
)


@pytest.mark.parametrize(
    ("url", "allowed"),
    [
        ("https://site.getnet.com.br/pix/", True),
        ("https://getnet.com.br/", True),
        ("http://site.getnet.com.br/pix/", False),
        ("https://getnet.com.br.evil.example/", False),
        ("https://evilgetnet.com.br/", False),
        ("ftp://site.getnet.com.br/a.pdf", False),
        ("https://user@getnet-taxa-zero.example.com/", False),
    ],
)
def test_domain_allowlist(url: str, allowed: bool) -> None:
    assert is_allowed(url, ["getnet.com.br"]) is allowed


async def test_crawl_respects_allowlist_robots_and_redirects() -> None:
    site = FakeSite()
    async with site.client() as client:
        pages = await Crawler(SOURCES, client).crawl()
    urls = {p.url for p in pages}
    assert urls == {
        f"{BASE}/maquininhas/",
        f"{BASE}/docs/guia-crediario.pdf",
        f"{BASE}/en/receivables-advance/",
        f"{BASE}/blog/receita-de-bolo/",
    }
    # Never requested: a domain outside the allowlist (seed, sitemap entry or redirect target)
    # and a path disallowed by robots.txt.
    assert OUTSIDE not in site.requested
    assert f"{BASE}/privado/interno/" not in site.requested


async def test_sitemap_lists_only_allowlisted_urls() -> None:
    site = FakeSite()
    async with site.client() as client:
        urls = await Crawler(SOURCES, client).sitemap_urls(SitemapSource(url=f"{BASE}/sitemap.xml"))
    assert f"{BASE}/maquininhas/" in urls
    assert OUTSIDE not in urls


async def test_sitemap_include_filter_and_page_limit() -> None:
    sources = SOURCES.model_copy(
        update={
            "seeds": [],
            "sitemaps": [SitemapSource(url=f"{BASE}/sitemap.xml", include=["maquininhas", "en/"])],
        }
    )
    async with FakeSite().client() as client:
        pages = await Crawler(sources, client).crawl()
        assert {p.url for p in pages} == {
            f"{BASE}/maquininhas/",
            f"{BASE}/en/receivables-advance/",
        }
        limited = await Crawler(sources.model_copy(update={"max_pages": 1}), client).crawl()
    assert len(limited) == 1


async def test_unreachable_robots_txt_blocks_the_host() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/robots.txt":
            return httpx.Response(503)
        return httpx.Response(200, text="<html><body><p>conteúdo</p></body></html>")

    async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as client:
        pages = await Crawler(SOURCES.model_copy(update={"sitemaps": []}), client).crawl()
    assert pages == []


def test_extract_html_keeps_structure_and_drops_boilerplate() -> None:
    html = (FIXTURES / "maquininhas.html").read_bytes()
    page = extract(f"{BASE}/maquininhas/", html, "text/html; charset=utf-8")
    assert page is not None
    assert "Maquininhas Getnet" in page.title
    assert page.lang == "pt"
    assert page.source_type == "page"
    assert "# Maquininhas Getnet" in page.text
    assert "## Comparativo" in page.text
    assert "| Pix na máquina |" in page.text
    assert "Fale conosco" not in page.text  # navigation removed


def test_extract_detects_english_pages() -> None:
    html = (FIXTURES / "receivables-advance-en.html").read_bytes()
    page = extract(f"{BASE}/en/receivables-advance/", html, "text/html")
    assert page is not None
    assert page.lang == "en"
    assert "Receivables advance" in page.text


def test_extract_pdf() -> None:
    pdf = (FIXTURES / "guia-crediario.pdf").read_bytes()
    page = extract(f"{BASE}/docs/guia-crediario.pdf", pdf, "application/pdf")
    assert page is not None
    assert page.source_type == "pdf"
    assert page.title == "Getnet - Guia do Crediario"
    assert "Codigo de recusa 51" in page.text


def test_extract_rejects_unsupported_or_empty_content() -> None:
    assert extract(f"{BASE}/x.png", b"\x89PNG", "image/png") is None
    assert extract(f"{BASE}/vazio/", b"<html><body></body></html>", "text/html") is None
    assert extract(f"{BASE}/quebrado.pdf", b"not a pdf", "application/pdf") is None


def test_configured_sources_are_allowlisted_and_cover_the_scenarios() -> None:
    sources = load_sources()
    assert sources.seeds
    for entry in [*sources.seeds, *sources.sitemaps]:
        assert is_allowed(entry.url, sources.allowed_domains), entry.url
    seeds = " ".join(s.url for s in sources.seeds)
    for topic in ("maquininha", "pix", "antecipacao", "crediario", "link-de-pagamento", "ajuda"):
        assert topic in seeds, topic
