"""Crawler for public Getnet content (research R-17, REQ-RAG-01).

Only https URLs under the domain allowlist are fetched, and only where robots.txt allows. Redirects
are followed by hand so every hop is checked again: a page on an allowed host cannot pull content
from elsewhere (threat model LLM04). HTML goes through trafilatura (boilerplate removed, headings
and tables kept as Markdown); PDFs through pypdf.
"""

import contextlib
import io
import re
from dataclasses import dataclass, replace
from pathlib import Path
from typing import Literal
from urllib.parse import urljoin, urlsplit
from urllib.robotparser import RobotFileParser
from xml.etree import ElementTree

import httpx
import trafilatura
import yaml
from pydantic import BaseModel, ConfigDict, Field
from pypdf import PdfReader

from app.observability.logging import get_logger

SOURCES_FILE = Path(__file__).with_name("sources.yaml")
USER_AGENT = "GetnetSupportBot/1.0 (knowledge-base ingestion)"
MAX_BYTES = 10 * 1024 * 1024
MAX_REDIRECTS = 5
_DISALLOW_ALL = ["User-agent: *", "Disallow: /"]

Lang = Literal["pt", "en"]
SourceType = Literal["page", "faq", "pdf"]


class _Config(BaseModel):
    model_config = ConfigDict(extra="forbid")


class Seed(_Config):
    url: str
    lang: Lang | None = None
    type: SourceType = "page"


class SitemapSource(_Config):
    url: str
    include: list[str] = Field(default_factory=list, description="URL substrings to keep")


class Sources(_Config):
    allowed_domains: list[str] = Field(min_length=1)
    seeds: list[Seed] = Field(default_factory=list)
    sitemaps: list[SitemapSource] = Field(default_factory=list)
    max_pages: int = Field(60, ge=1)


@dataclass(frozen=True)
class Page:
    url: str
    title: str
    lang: Lang
    source_type: SourceType
    text: str


def load_sources(path: Path = SOURCES_FILE) -> Sources:
    return Sources.model_validate(yaml.safe_load(path.read_text(encoding="utf-8")))


def is_allowed(url: str, domains: list[str]) -> bool:
    """https, no credentials, and the host is an allowed domain or one of its subdomains."""
    parts = urlsplit(url)
    host = (parts.hostname or "").lower()
    if parts.scheme != "https" or parts.username or parts.password or not host:
        return False
    return any(host == d or host.endswith(f".{d}") for d in domains)


_HTML_LANG = re.compile(rb"<html[^>]*\blang=[\"']?([a-zA-Z]{2})", re.I)
_HEADING = re.compile(r"^#{1,6}\s+(.+)$", re.M)


def _url_lang(url: str) -> Lang:
    return "en" if "/en/" in urlsplit(url).path.lower() + "/" else "pt"


def _extract_html(url: str, body: bytes) -> Page | None:
    html = body.decode("utf-8", errors="replace")
    text = trafilatura.extract(
        html,
        url=url,
        output_format="markdown",
        include_tables=True,
        include_formatting=True,
        favor_recall=True,
    )
    if not text or not text.strip():
        return None
    meta = trafilatura.extract_metadata(html)
    heading = _HEADING.search(text)
    title = (meta.title if meta and meta.title else None) or (heading and heading.group(1)) or url
    found = _HTML_LANG.search(body[:2048])
    lang: Lang = ("en" if found.group(1).lower() == b"en" else "pt") if found else _url_lang(url)
    return Page(url=url, title=title.strip(), lang=lang, source_type="page", text=text.strip())


def _extract_pdf(url: str, body: bytes) -> Page | None:
    try:
        reader = PdfReader(io.BytesIO(body))
        text = "\n\n".join((p.extract_text() or "").strip() for p in reader.pages).strip()
        meta_title = reader.metadata.title if reader.metadata else None
    except Exception as exc:  # malformed PDF: skip the document, keep the run going
        get_logger().warning("crawl_pdf_unreadable", url=url, error=type(exc).__name__)
        return None
    if not text:
        return None
    title = meta_title or next(line.strip() for line in text.splitlines() if line.strip())
    return Page(url=url, title=title, lang=_url_lang(url), source_type="pdf", text=text)


def extract(url: str, body: bytes, content_type: str) -> Page | None:
    content_type = content_type.lower()
    if "pdf" in content_type:
        return _extract_pdf(url, body)
    if "html" in content_type:
        return _extract_html(url, body)
    return None


class Crawler:
    def __init__(self, sources: Sources, client: httpx.AsyncClient) -> None:
        self.sources = sources
        self.client = client
        self._robots: dict[str, RobotFileParser] = {}

    async def allowed_by_robots(self, url: str) -> bool:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            rules = _DISALLOW_ALL  # forbidden or unreachable robots.txt: be conservative
            with contextlib.suppress(httpx.HTTPError):
                resp = await self.client.get(
                    f"{origin}/robots.txt",
                    headers={"User-Agent": USER_AGENT},
                    follow_redirects=False,
                )
                if resp.status_code == 200:
                    rules = resp.text.splitlines()
                elif 400 <= resp.status_code < 500 and resp.status_code not in (401, 403):
                    rules = []  # no robots.txt: everything is allowed
            parser = RobotFileParser()
            parser.parse(rules)
            self._robots[origin] = parser
        return self._robots[origin].can_fetch(USER_AGENT, url)

    async def _get(self, url: str) -> httpx.Response | None:
        for _ in range(MAX_REDIRECTS + 1):
            if not is_allowed(url, self.sources.allowed_domains):
                get_logger().info("crawl_skipped", url=url, reason="not_allowlisted")
                return None
            if not await self.allowed_by_robots(url):
                get_logger().info("crawl_skipped", url=url, reason="robots_txt")
                return None
            resp = await self.client.get(
                url, headers={"User-Agent": USER_AGENT}, follow_redirects=False
            )
            if resp.is_redirect:
                url = urljoin(url, resp.headers.get("location", ""))
                continue
            if resp.status_code != 200 or len(resp.content) > MAX_BYTES:
                get_logger().info("crawl_skipped", url=url, reason=f"http_{resp.status_code}")
                return None
            return resp
        return None

    async def fetch(self, url: str, seed: Seed | None = None) -> Page | None:
        try:
            resp = await self._get(url)
        except httpx.HTTPError as exc:
            get_logger().warning("crawl_failed", url=url, error=type(exc).__name__)
            return None
        if resp is None:
            return None
        page = extract(str(resp.url), resp.content, resp.headers.get("content-type", ""))
        if page is None or seed is None:
            return page
        source_type: SourceType = (
            "pdf" if page.source_type == "pdf" else ("faq" if seed.type == "faq" else "page")
        )
        return replace(page, lang=seed.lang or page.lang, source_type=source_type)

    async def sitemap_urls(self, sitemap: SitemapSource, nested: bool = False) -> list[str]:
        try:
            resp = await self._get(sitemap.url)
        except httpx.HTTPError:
            resp = None
        if resp is None:
            return []
        try:
            # Python 3.12's expat neither resolves external entities nor expands entities
            # without limit, so a hostile sitemap cannot read files or exhaust memory.
            root = ElementTree.fromstring(resp.content)  # noqa: S314
        except ElementTree.ParseError:
            get_logger().warning("sitemap_unreadable", url=sitemap.url)
            return []
        locs = [el.text.strip() for el in root.iter() if el.tag.endswith("loc") and el.text]
        if root.tag.endswith("sitemapindex"):
            if nested:  # one level of sitemap index is enough; never loop
                return []
            nested_urls: list[str] = []
            for loc in locs:
                nested_urls += await self.sitemap_urls(
                    sitemap.model_copy(update={"url": loc}), True
                )
            return nested_urls
        return [
            u
            for u in locs
            if is_allowed(u, self.sources.allowed_domains)
            and (not sitemap.include or any(s in u for s in sitemap.include))
        ]

    async def crawl(self) -> list[Page]:
        targets: list[tuple[str, Seed | None]] = [(s.url, s) for s in self.sources.seeds]
        for sitemap in self.sources.sitemaps:
            targets += [(u, None) for u in await self.sitemap_urls(sitemap)]
        pages: dict[str, Page] = {}
        tried: set[str] = set()
        for url, seed in targets:
            if len(pages) >= self.sources.max_pages:
                break
            if url in tried:
                continue
            tried.add(url)
            page = await self.fetch(url, seed)
            if page is not None and page.url not in pages:
                pages[page.url] = page
        return list(pages.values())
