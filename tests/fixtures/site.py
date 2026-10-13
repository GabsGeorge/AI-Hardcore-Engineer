"""Offline copy of a tiny Getnet site served through httpx.MockTransport (no network in tests)."""

from pathlib import Path

import httpx

FIXTURES = Path(__file__).parent
BASE = "https://site.getnet.com.br"
OUTSIDE = "https://getnet-taxa-zero.example.com/promo/"

ROUTES: dict[str, tuple[str, str]] = {
    f"{BASE}/robots.txt": ("robots.txt", "text/plain"),
    f"{BASE}/sitemap.xml": ("sitemap.xml", "application/xml"),
    f"{BASE}/maquininhas/": ("maquininhas.html", "text/html; charset=utf-8"),
    f"{BASE}/en/receivables-advance/": ("receivables-advance-en.html", "text/html; charset=utf-8"),
    f"{BASE}/docs/guia-crediario.pdf": ("guia-crediario.pdf", "application/pdf"),
    f"{BASE}/privado/interno/": ("maquininhas.html", "text/html; charset=utf-8"),
    f"{BASE}/blog/receita-de-bolo/": ("maquininhas.html", "text/html; charset=utf-8"),
    OUTSIDE: ("fora-da-allowlist.html", "text/html; charset=utf-8"),
}
REDIRECTS = {f"{BASE}/antigo/": OUTSIDE}


class FakeSite:
    """Serves the fixtures and records every requested URL. `overrides` replaces a page body."""

    def __init__(self) -> None:
        self.requested: list[str] = []
        self.overrides: dict[str, bytes] = {}

    def handler(self, request: httpx.Request) -> httpx.Response:
        url = str(request.url)
        self.requested.append(url)
        if url in REDIRECTS:
            return httpx.Response(301, headers={"Location": REDIRECTS[url]})
        if url not in ROUTES:
            return httpx.Response(404, text="not found")
        name, content_type = ROUTES[url]
        body = self.overrides.get(url) or (FIXTURES / name).read_bytes()
        return httpx.Response(200, content=body, headers={"Content-Type": content_type})

    def client(self) -> httpx.AsyncClient:
        return httpx.AsyncClient(transport=httpx.MockTransport(self.handler), follow_redirects=True)
