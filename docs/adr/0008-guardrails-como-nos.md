# ADR 0008: Guardrails como nós do grafo, fora dos especialistas

- **Status**: Aceito · **Data**: 2026-10-13 · **Requisitos**: REQ-GR-01..05

## Contexto

Regras de segurança dentro dos prompts dos especialistas são contornáveis e difíceis de testar.

## Decisão

`input_guardrail` (máscara de PII, heurísticas, classificador LLM) antes do Supervisor e
`output_guardrail` (PII, promessas, grounding) antes do END, como nós próprios com testes
isolados. Um bloqueio na entrada vai para `safe_response`, sem acionar especialistas.

## Alternativas

- **Regras nos prompts**: zero custo extra, mas sem garantia nem teste isolado.
- **NeMo Guardrails / LLM Guard**: dependências e modelos pesados.

## Consequências

- (+) Políticas centralizadas, testáveis e auditáveis.
- (−) Uma chamada LLM extra por mensagem (classificador) e outra para o grounding das respostas do
  Knowledge.
