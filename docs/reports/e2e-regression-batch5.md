# Regressão do batch 5

**Data:** 2026-11-02, cerca de 14:07–14:14 (horário do navegador)
**Ambiente:** `http://localhost/`, viewport de 894×529, sem ajustes no stream
**Conta:** `lojista.qa@getnet.example.com`

## Resumo

| Teste | Resultado | Rota | `trace_id` |
|---|---|---|---|
| Pré-check da build | OK | N/A | N/A |
| 1. Guardrail em "vendas de ontem" | OK | `input_guardrail` → `supervisor` → `support` → `supervisor` → `synthesize` → `output_guardrail` | `e86816e50a861f70b9f74103e76e89a6` |
| 2. Markdown com a pergunta pedida | FAIL | `input_guardrail` → `safe_response` | `736a0aba13c1cec1472702397eff3ff9` e `af6a027775c5ae7c3508f5b7cac4b652` |
| 3. Sem bolha vazia em handoff | OK | `input_guardrail` → `supervisor` | `9ef0c11872396decc76df0c0bd2fe0c0` |
| 4. Auto-scroll com composer visível | FAIL | Ver detalhes | `a10db9458d60421c3153241d1b7e41ff` e `18385ddd8c4e84f4381f8c7253bca432` |

**Score: 6/10.** O guardrail de vendas, a bolha vazia e o renderizador de Markdown foram corrigidos. O Histórico também melhorou. Ainda assim, a pergunta sobre vantagens é bloqueada, o composer sai da tela e a busca de conhecimento segue expirando.

## Regressões e efeitos colaterais

| Prioridade | Item | Evidência |
|---|---|---|
| **P0** | `search_knowledge_base` continua expirando; o caso longo teve 16 timeouts | `18385ddd8c4e84f4381f8c7253bca432` |
| **P0** | Pergunta de produto com "bullets" sobre antecipação é bloqueada | Teste 2 |
| **P1** | Toda mensagem em conversa com handoff ativo volta para handoff sem resposta | `a10db9458d60421c3153241d1b7e41ff` |
| **P1** | Um 502 em `/v1/auth/me` ao carregar `/chat` manda para `/login?next=/chat` | Observado uma vez |
| **P1** | Composer fica fora da tela após resposta em conversa longa | Teste 4 |
| **P1** | Aviso de handoff fica fora da tela em conversa longa | Teste 3 |
| **P2** | Resposta expõe "obtidas das respostas dos especialistas" | Screenshot 03 |
| **P2** | Espaço extra de 24 px acima do composer na tela inicial | Campo em y=165 |
| **P2** | Sem streaming de texto: só chegam passos, handoff e `done` | Todas as execuções |

## Melhorias confirmadas

- Histórico mostra prévia da mensagem
- Abrir conversa pelo clique carrega o conteúdo
- Markdown funciona (lista com 3 bullets em `ul>li` nativo renderizou corretamente)
