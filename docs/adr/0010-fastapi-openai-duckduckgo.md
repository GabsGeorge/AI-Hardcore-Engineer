# ADR 0010: FastAPI em vez de Django; OpenAI (GPT) e DuckDuckGo

- **Status**: Aceito · **Data**: 2026-10-13 · **Requisitos**: REQ-API-*, REQ-REL-02, REQ-RAG-08

## Contexto

As alternativas eram Django e Azure OpenAI. Em 2026-10-13 o usuário confirmou a API da OpenAI direta, com
modelos GPT, e o DuckDuckGo para web search.

## Decisão

- **API**: FastAPI + Pydantic v2 (async, OpenAPI automático, validação forte).
- **LLM**: API da OpenAI com modelo GPT principal e fallback configuráveis por ambiente;
  embeddings `text-embedding-3-small`.
- **Web search**: DuckDuckGo (`ddgs`) com cache, timeout e circuit breaker.

## Alternativas

- **Django**: admin pronto, mas síncrono por padrão e mais pesado para uma API de agentes.
- **Azure OpenAI**: alinhado ao ambiente Getnet, descartado pelo usuário.
- **Tavily**: feito para agentes, mas exige chave; descartado pelo usuário.

## Consequências

- (+) Stack enxuta e async de ponta a ponta; uma única chave externa.
- (−) Sem admin pronto: o console do operador fica na feature 002. O DuckDuckGo não tem SLA e exige
  degradação honesta.
