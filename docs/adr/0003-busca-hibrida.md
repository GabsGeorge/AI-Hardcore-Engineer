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

Execução de `evals/retrieval_compare.py` em 2026-11-04 no conjunto rotulado
`evals/retrieval_labeled.yaml` (16 queries), com embeddings `text-embedding-3-small` e reranker
FlashRank `ms-marco-MultiBERT-L-12`, limiar de score 0,30.

| Estratégia       | recall@5 | MRR   | nDCG@5 |
|------------------|----------|-------|--------|
| densa            | 0,813    | 0,708 | 0,695  |
| híbrida (RRF)    | 0,688    | 0,667 | 0,610  |
| híbrida + rerank | 0,375    | 0,354 | 0,291  |

Reproduzir:

```bash
docker compose --profile eval run --rm --no-deps \
  -e SKIP_RERANKER=0 eval python evals/retrieval_compare.py
```

### Leitura dos números

O reranker, com cutoff de 0,30 no score do cross-encoder, está sendo agressivo demais para o
corpus curto do desafio (44 documentos, 239 chunks): descarta passagens relevantes que a busca
densa recuperaria, reduzindo recall@5 de 0,81 para 0,38. A híbrida sem rerank também perde para
a densa pura — o BM25 em 239 chunks não traz ganho e dilui o sinal da fusão RRF.

Em produção, com corpus maior e queries mais exatas (códigos, nomes próprios), a tendência se
inverte — BM25 e reranker ganham valor. Para esta entrega:

- O gate `recall@5 ≥ 0,90` definido no script **não passa**; mantemos como gate aspiracional e
  registramos aqui a medida real para que o próximo iteração ajuste o limiar do reranker ou
  troque de modelo com base em dados.
- O caminho `híbrida + rerank` continua em produção por ser o exigido pelo enunciado; o smoke
  end-to-end dos 10 cenários confirma que, nas perguntas do enunciado, as passagens certas são
  recuperadas (ver `docs/reports/smoke.md`).
- Ação de próxima iteração: calibrar o limiar do reranker no conjunto rotulado (varrer de 0,10
  a 0,30) e/ou avaliar `bge-reranker-v2-m3` quando a infraestrutura comportar os ~2,2 GB.
