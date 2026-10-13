# ADR 0009: Prompts versionados em arquivo com hash no trace

- **Status**: Aceito · **Data**: 2026-10-13 · **Requisitos**: REQ-OBS-02

## Contexto

Mudanças de prompt alteram a qualidade e precisam ser rastreáveis até a regressão.

## Decisão

Um arquivo Markdown por prompt em `prompts/`, carregado no startup; o `sha256[:12]` do conteúdo vai
como `prompt.version` em cada span de LLM e nos resultados de avaliação.

## Alternativas

- **Prompts inline no código**: diffs misturados com lógica.
- **Gerenciador de prompts do Langfuse**: dependência de runtime do serviço de observabilidade.

## Consequências

- (+) Diffs legíveis e correlação entre versão de prompt e métricas.
- (−) Mais um diretório para manter.
