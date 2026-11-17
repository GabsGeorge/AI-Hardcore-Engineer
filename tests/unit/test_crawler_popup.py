"""The site's "Vamos começar o seu atendimento?" pop-up is on every help page and the extractor
keeps it. It must not open the text of each page: it dilutes what the page is about (REQ-RAG-01)."""

import pytest

from app.rag.crawler import extract

pytestmark = pytest.mark.req("REQ-RAG-01")

POPUP = (
    "<div><p>Vamos começar o seu atendimento?</p><p>Ainda não é cliente?</p>"
    "<p>Adquira agora e venda mais!</p><p>CENTRAL DE VENDAS</p><p>Já é nosso cliente?</p>"
    "<p>CENTRAL DE AJUDA</p><p>Nos informe CPF ou CNPJ</p>"
    "<p>Para melhor direcionamento, informe o documento solicitado.</p></div>"
)
ARTICLE = (
    "<article><h1>Erro ADQ 4-91: erro na aprovação da venda</h1>"
    "<p>Caso sua maquininha apresente um Erro ADQ na tela, você mesmo pode solucioná-lo "
    "rapidamente. Clique na tecla de Função, insira o número 38 e aguarde a tela ficar verde "
    "confirmando a ação. Depois selecione a opção de reiniciar o terminal e teste uma venda.</p>"
    "</article>"
)


def _page(html_body: str) -> str:
    head = "<head><title>Erro ADQ 4-91 - Getnet</title></head>"
    return f"<html lang='pt'>{head}<body>{html_body}</body></html>"


def test_popup_text_is_removed_and_the_article_is_kept() -> None:
    page = extract(
        "https://site.getnet.com.br/get-ajuda-erros-maquininha/erro-adq-4-91/",
        _page(POPUP + ARTICLE).encode(),
        "text/html",
    )
    assert page is not None
    assert "Vamos começar" not in page.text and "informe o documento solicitado" not in page.text
    assert "tecla de Função" in page.text and "número 38" in page.text


def test_page_without_the_popup_is_unchanged() -> None:
    page = extract(
        "https://site.getnet.com.br/get-ajuda-erros-maquininha/erro-adq-4-91/",
        _page(ARTICLE).encode(),
        "text/html",
    )
    assert page is not None and "tecla de Função" in page.text
