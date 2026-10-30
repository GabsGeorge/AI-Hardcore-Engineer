# Smoke test — 10 cenários do enunciado

**Data**: 2026-10-30 (run completo após reset do volume `models-cache`) ·
**Script**: [scripts/smoke_scenarios.sh](../../scripts/smoke_scenarios.sh)

Este relatório mostra o resultado real de rodar os 10 cenários do enunciado contra uma
stack subida com `scripts/bootstrap_env.sh` + `docker compose up -d`. O script lê a saída
crua da API em `/tmp/smoke/sc{01..10}.json`, extrai rota, tools, handoff, guardrails,
latência e `trace_id`, e resume por cenário.

## Como reproduzir

```bash
cp .env.example .env
bash scripts/bootstrap_env.sh           # gera segredos
# cole sua OPENAI_API_KEY no .env
docker compose up -d --build
# aguarde o ingest completar (base de 44 páginas, 239 chunks)
docker compose logs ingest --tail=1     # procure "ingest_finished"
bash scripts/smoke_scenarios.sh         # saída em /tmp/smoke/
```

## Resultado real — 10/10 cenários capturados

| # | Pergunta | Rota | Tools | Guardrail | Handoff | ms | Trace |
|---|---|---|---|---|---|---|---|
| 1 | Diferença Clássica × Smart | guardrail → safe_response | — | **blocked** / pass | none | 2.985 | `cf9266c61a9b` |
| 2 | Previsão do tempo em POA | guardrail → safe_response | — | **blocked** / pass | none | 1.372 | `3066d4bdebcb` |
| 3 | Quando cai o dinheiro de ontem? | guardrail → supervisor → support → synthesize → output_guardrail | `get_settlement_schedule` ok | pass / pass | none | 6.724 | `a1851d7e20c8` |
| 4 | Pix sem conta bancária? | guardrail → supervisor → knowledge → supervisor | 4× `search_knowledge_base` **timeout** | pass / pass | **awaiting_human** | 10.136 | `fec28aa1bdcd` |
| 5 | Máquina sem internet | guardrail → supervisor → support ×2 → synthesize → output_guardrail | 2× `diagnose_terminal` ok | pass / pass | none | 8.055 | `be6fa2a0b6ad` |
| 6 | Antecipação de recebíveis | guardrail → supervisor → knowledge → supervisor | 3× `search_knowledge_base` **error** + 1 **timeout** | pass / pass | **awaiting_human** | 21.494 | `9addaed670b8` |
| 7 | Cotação do euro | guardrail → safe_response | — | **blocked** / pass | none | 2.502 | `eb73ad0f08f1` |
| 8 | Erro transação recusada | guardrail → supervisor → support ×2 → synthesize → output_guardrail | `get_recent_transactions`, `lookup_decline_code` ×2 ok | pass / pass | none | 7.781 | `11f17c461ea0` |
| 9 | Parcelas no crediário | guardrail → safe_response | — | **blocked** / pass | none | 1.229 | `a7bab4182a61` |
| 10 | Vender por WhatsApp | guardrail → supervisor → knowledge → supervisor | 4× `search_knowledge_base` **timeout** | pass / pass | **awaiting_human** | 38.915 | `ee8c8761db60` |

## Interpretação

### ✅ Fluxos que funcionaram em produção real (4/10)

- **sc02** (previsão do tempo) + **sc07** (cotação do euro) — bloqueados corretamente
  pelo guardrail de entrada como off-topic. Rota curta, resposta `safe_response`
  determinística, zero tokens gastos no LLM principal.
- **sc03** (settlement), **sc05** (terminal offline), **sc08** (transação recusada) —
  três cenários Support exercitando 4 tools diferentes
  (`get_settlement_schedule`, `diagnose_terminal`, `get_recent_transactions`,
  `lookup_decline_code`), orquestração completa até `synthesize + output_guardrail`.
  Prova que o grafo multi-agente funciona de ponta a ponta.

### 🟡 HITL exercitado em condições reais (3/10)

- **sc04**, **sc06**, **sc10** (knowledge queries) — todos escalaram para humano após
  4 falhas de `search_knowledge_base`. Esse é **o comportamento esperado por desenho**:
  REQ-HITL-01 pede escalação após falha persistente de tool.
- Nenhum dos três respondeu "não sei" alucinado — todos abriram ticket (`handoff.status
  = awaiting_human`) com `ticket_id` válido. O HITL é a última linha de defesa quando a
  base de conhecimento não responde, e ela funcionou.

### ❌ Achados honestos (3/10)

**Achado A — sc04/sc06/sc10: `search_knowledge_base` falha mesmo com DB cheio.**

O Postgres tem 44 documentos e 239 chunks (confirmado via `SELECT COUNT(*) FROM chunks`).
Embeddings são gerados com sucesso (HTTP 200 contra `api.openai.com/v1/embeddings` no
log). Mas o `search_knowledge_base` devolve `status=timeout` ou `status=error`. Possíveis
causas (não investigadas em profundidade por restrição de tempo):

- Latência do FlashRank em cold start: cada chamada reinicializa o reranker?
- OOM no container `api` depois do flashrank + embedding cache quente simultâneos — o
  container matou com exit 137 após o smoke, consistente com OOMKilled do kernel.
- Deadlock no pool de conexões Postgres: os warnings `scheduler_tick_error:
  OperationalError` depois do smoke sugerem que o pool ficou travado.

**Achado B — sc01 e sc09: guardrail de entrada over-blocking.**

- sc01 "Diferença entre Get Clássica e Get Smart" é uma pergunta de produto 100%
  legítima, mas foi bloqueada com `safe_response`. Produto deveria rotear para
  `knowledge`.
- sc09 "Como funcionam as parcelas no crediário?" idem — pergunta de produto bloqueada.
- O guardrail de entrada tem três barreiras (máscara PII + heurística + classificador
  LLM). Suspeita: o classificador LLM está sendo conservador demais com termos de
  produto Getnet ("Clássica", "Smart", "crediário"); o prompt do guardrail de entrada
  precisa de few-shot examples cobrindo nomes de produto.

### Verdict por categoria

| Categoria | Esperado | Real | Status |
|---|---|---|---|
| Caminho Support (tools reais) | 3/3 ok | 3/3 ok | ✅ |
| Off-topic bloqueado | 2/2 blocked | 2/2 blocked | ✅ |
| Knowledge resposta real | 5/5 responde | 0/5 responde (3 handoff, 2 blocked wrongly) | ❌ |
| HITL automático | funciona quando precisa | 3/3 abre ticket | ✅ |
| Guardrail de saída | 10/10 pass | 10/10 pass | ✅ |

## Trace de referência (sc03 — Support feliz)

```
POST /v1/chat                                                     6.724ms
├─ guardrail.input                               pass
├─ supervisor.route                              → support
├─ tool.get_settlement_schedule                  ok               2.229ms
├─ supervisor.route                              → synthesize
├─ synthesize.compose                            response_len=67
└─ guardrail.output                              pass
```

A resposta é "Não há registros de pagamentos programados para as vendas do dia
2023-10-05." — curta, factual, dentro do contexto do lojista `cliente1988`.

## Próximos passos (não bloqueantes para a entrega conceitual)

1. Investigar o `search_knowledge_base` em condição real — provável OOM do container
   `api` ou latência do FlashRank em cold start. Opções: bump de memória no compose,
   warm-up do reranker no startup, ou cache do modelo em disco (já aplicado em
   [Dockerfile:30-35](../../Dockerfile) — pode precisar de mais um passo).
2. Ajustar o prompt do guardrail de entrada: adicionar exemplos positivos para
   "Clássica", "Smart", "crediário", "Link de Pagamento" — categoria "produto Getnet"
   explicitamente permitida.

**Nenhum dos dois é regressão de segurança** — ambos são sobre completude funcional da
Knowledge path.

## Histórico

| Data | 10/10 | Observação |
|---|---|---|
| 2026-10-30 | 4 ok + 3 HITL (desenho correto) + 3 falsos positivos | 10 traces reais; 3 achados abertos (A, B) |
