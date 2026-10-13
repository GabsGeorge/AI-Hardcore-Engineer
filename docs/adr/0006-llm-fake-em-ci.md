# ADR 0006: LLM fake determinístico em CI; LLM real só em avaliação

- **Status**: Aceito · **Data**: 2026-10-13 · **Requisitos**: REQ-INF-03, REQ-OBS-06, constitution VI

## Contexto

O avaliador precisa rodar os testes sem chave nem rede. Testes com LLM real são lentos, caros,
instáveis e exigem chave.

## Decisão

Os nós obtêm modelos por `get_model(role)`; nos testes, um fake roteirizado por nó devolve as
saídas estruturadas definidas em cada teste. Embeddings e reranker também têm fakes. Postgres e
Redis reais rodam numa rede Docker `internal: true`, sem saída externa. A qualidade real é medida
por um job de avaliação com modelo real (golden set, RAGAS, retrieval) que bloqueia regressões.

## Alternativas

- **LLM real em todos os testes**: mede qualidade, mas é não determinístico e exige rede.
- **Gravação de respostas (VCR)**: frágil a mudanças de prompt.

## Consequências

- (+) `make test` roda offline, rápido e reprodutível.
- (−) Testes de grafo não medem qualidade de resposta; isso fica com a avaliação.
