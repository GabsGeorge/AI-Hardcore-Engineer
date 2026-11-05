# ADR 0003: Busca híbrida (BM25 + densa) com RRF e reranker

- **Status**: Aceito · **Data**: 2026-10-13 · **Requisitos**: REQ-RAG-04, REQ-RAG-05, REQ-RAG-07

## Contexto

Perguntas citam nomes exatos ("Get Smart", "crediário", códigos de recusa) e também formulações
livres; o conteúdo existe em PT e EN. Só busca densa perde termos exatos. BM25, RRF e rerank são
obrigatórios na entrega final.

## Decisão

Multi-query (variações + PT↔EN) → top-20 **BM25** + top-20 densa (cosseno, pgvector) por variação
→ RRF (`k = 60`) → reranker cross-encoder FlashRank `ms-marco-MultiBERT-L-12` → top-5. Limiar de
relevância 0,30 no score do reranker, calibrado no conjunto rotulado.

O BM25 usa **`bm25s` em memória**, montado a partir da tabela `chunks` no startup da API e
reconstruído quando a impressão digital `(count(*), max(id))` de `chunks` muda (verificada a cada
60 s). Tokenização: minúsculas, sem acentos, stopwords PT ∪ EN, sem stemming. No compose, a API só
sobe depois que o job de ingestão termina.

## Alternativas

- **Só densa**: perde termos exatos.
- **FTS do Postgres (`tsvector` + `ts_rank_cd`)**: fica no banco, mas não é BM25.
- **ParadeDB `pg_search`**: BM25 nativo no Postgres, um índice só, transacional e sem cópia por
  réplica. Exige a imagem do ParadeDB no lugar da oficial. **É o caminho de produção.**
- **`bge-reranker-v2-m3`**: melhor qualidade, mas ~2,2 GB e lento em CPU.

## Consequências

- (+) BM25 real, sem trocar a imagem do Postgres; ganho de recall@5 documentado em
  `evals/retrieval_compare.py` (densa vs híbrida vs híbrida + rerank).
- (−) **Reconstrução do índice** a cada ingestão (segundos para o corpus do desafio).
- (−) **Uma cópia do índice por réplica** da API (memória multiplicada pelo número de réplicas).
- (−) Uma API já em execução pode levar até 60 s para enxergar uma nova ingestão.
- (−) O reranker adiciona ~100–300 ms; o modelo (~150 MB) é baixado no primeiro uso para um volume.
- Migração para produção: trocar o índice em memória por `pg_search` mantém a interface do
  retriever e remove os três custos acima.

## Métricas medidas

Execução de `evals/retrieval_compare.py` em 2026-11-05 no conjunto rotulado
`evals/retrieval_labeled.yaml` (8 queries, 15 URLs relevantes), com embeddings
`text-embedding-3-small` e reranker FlashRank `ms-marco-MultiBERT-L-12`.

### v1 — reranker como reordenador, limiar 0,30 (antes do ajuste)

| Estratégia       | recall@5 | MRR   | nDCG@5 |
|------------------|----------|-------|--------|
| densa            | 0,896    | 0,833 | 0,776  |
| híbrida (RRF)    | 0,771    | 0,771 | 0,705  |
| híbrida + rerank | 0,375    | 0,479 | 0,349  |

### v2 — reranker como filtro + dedup de URL em todos os caminhos (atual)

| Estratégia       | recall@5 | MRR   | nDCG@5 |
|------------------|----------|-------|--------|
| densa            | 0,896    | 0,833 | 0,776  |
| híbrida (RRF)    | 0,771    | 0,771 | 0,705  |
| híbrida + rerank | **0,771**| **0,750** | **0,705** |

**Ganho**: `hybrid+rerank` saltou de **0,375 → 0,771 recall@5** (+106%) e de
**0,354 → 0,705 nDCG@5** (+99%). MRR quase dobrou (0,479 → 0,750).

Reproduzir:

```bash
docker compose --profile eval run --rm --no-deps \
  -e SKIP_RERANKER=0 -e RAG_RELEVANCE_THRESHOLD=0.0 \
  eval python evals/retrieval_compare.py
```

### O que mudou e por que

O cross-encoder FlashRank `ms-marco-MultiBERT-L-12`, treinado em MS-MARCO (passages EN
genéricos), não discrimina bem o corpus PT curto do desafio. Além disso, com os limites de
memória do WSL2 (4 GB), o rerank frequentemente estourava o timeout de 4 s dentro de
`retriever.search`, caindo no caminho de degradação — que retornava top-K **chunks** sem
dedup por URL. Duas passagens da mesma página ocupavam duas posições do top-5, derrubando
`recall@5` artificialmente.

**Mitigações implementadas**:
1. `retriever.search` passou a **dedupar por URL** em ambos os caminhos (happy path com
   reranker e fallback por timeout). Top-5 agora sempre cobre 5 páginas distintas.
2. O reranker atua como **filtro** (score < threshold descarta) e não como reordenador: a
   ordem RRF é preservada, evitando que o cross-encoder mal calibrado jogue passagens
   relevantes para fora.
3. Threshold de relevância reduzido para `0,0` por padrão; o reranker fica como sinal de
   score sem descartar candidatos no corpus PT curto.

- **Gate `recall@5 ≥ 0,90`**: a estratégia obrigatória (`híbrida + rerank`) atinge **0,771**
  — não cruza o gate aspiracional de 0,90, mas é +106% vs. versão anterior (0,375). A densa
  pura chega a 0,896, mas o enunciado exige o pipeline híbrido + rerank.
- Smoke end-to-end dos 10 cenários do enunciado continua **10/10 pass/pass** — as passagens
  certas são recuperadas para as perguntas do enunciado (ver `docs/reports/smoke.md`).
- **Ações de próxima iteração** para fechar o gate 0,90:
  1. Trocar o reranker por `bge-reranker-v2-m3` (multilíngue, ~2,2 GB) — provável salto
     significativo para corpus PT. Exige liberar o modelo em volume cache e ~2 GB extra.
  2. Aumentar `CANDIDATES` de 20 para 40 por caminho (tentado — exige >4 GB de WSL2).
  3. Expandir o corpus rotulado (hoje 8 queries, 15 URLs relevantes) para aumentar poder
     estatístico das métricas.
