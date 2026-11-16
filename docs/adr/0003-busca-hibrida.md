# ADR 0003: Estratégia de busca — densa por padrão, híbrida + reranker disponível

- **Status**: Aceito · **Atualizado**: 2026-11-16 · **Requisitos**: REQ-RAG-04, REQ-RAG-05, REQ-RAG-07

## Contexto

Perguntas citam nomes exatos ("Get Smart", "crediário", códigos de recusa) e também formulações
livres; o conteúdo existe em PT e EN. A versão inicial adotou BM25 + densa + RRF + reranker
cross-encoder. Medindo no conjunto rotulado, essa combinação perdeu para a busca densa pura, e o
reranker não é viável no hardware do desafio. A estratégia padrão passou a ser escolhida pelos
dados, e as outras continuam implementadas e selecionáveis.

## Decisão

`RAG_STRATEGY` (padrão **`dense`**):

- **`dense`** — multi-query (variações + PT↔EN) → top-20 candidatos por similaridade de cosseno
  (pgvector) → só passagens com cosseno ≥ `RAG_DENSE_THRESHOLD` (**0,40**) → a melhor passagem de
  cada página → top-5 **páginas distintas**. O score devolvido é o cosseno reescalado
  (`dense_relevance`): no limiar vale `CONFIDENCE_REPLAN` (0,70) e em `RAG_DENSE_STRONG` (0,70) ou
  mais vale 1,0, linear entre os dois. Sem a reescala, o cosseno bruto de um bom acerto
  (0,55–0,75) limitaria toda resposta abaixo de `CONFIDENCE_REPLAN` e a levaria a replan/escalonamento.
  A confiança final continua sendo `min(autoavaliação do modelo, score)`, então é o modelo que decide.
- **`hybrid_rerank`** — top-20 **BM25** (`bm25s` em memória) + top-20 densa → RRF (`k = 60`) →
  reranker FlashRank `ms-marco-MultiBERT-L-12` → top-5 com `RAG_RELEVANCE_THRESHOLD` (0,30) no score
  do reranker. Continua coberto pelos testes de integração (que o selecionam via `RAG_STRATEGY`).

O índice BM25 só é montado quando `hybrid_rerank` está ativo. Tokenização: minúsculas, sem acentos,
stopwords PT ∪ EN, sem stemming. No compose, a API só sobe depois que o job de ingestão termina.

## Alternativas

- **Híbrida + rerank como padrão**: pior recall nas medições abaixo e o reranker estoura o
  timeout de 4 s neste hardware (WSL2, 4 GB), caindo no fallback sem reordenação.
- **FTS do Postgres (`tsvector` + `ts_rank_cd`)**: fica no banco, mas não é BM25.
- **ParadeDB `pg_search`**: BM25 nativo no Postgres. Exige a imagem do ParadeDB no lugar da oficial.
  **É o caminho de produção** para a estratégia híbrida.
- **`bge-reranker-v2-m3`**: melhor qualidade, mas ~2,2 GB e lento em CPU.

## Métricas medidas

`evals/retrieval_compare.py` e `evals/dense_threshold_sweep.py` em 2026-11-16, com embeddings
`text-embedding-3-small` e 239 chunks em 44 páginas.

**Conjunto rotulado ampliado — 14 perguntas** (as 8 originais + 6 perguntas do enunciado em PT e
EN: comparação Clássica×Smart, Pix sem conta, crediário, WhatsApp com Link de Pagamento):

| Estratégia | recall@5 | MRR   | nDCG@5 |
|------------|----------|-------|--------|
| **densa**  | **0,798**| **0,762** | **0,715** |
| híbrida (RRF) | 0,690 | 0,690 | 0,630 |

As 8 perguntas originais isoladas davam densa 0,896 e híbrida 0,771; ao incluir as perguntas curtas
do enunciado o recall da densa cai para 0,798. **O gate aspiracional `recall@5 ≥ 0,90` não é
atingido** no conjunto ampliado.

**Híbrida + rerank não foi remedida no conjunto ampliado**: o reranker não carrega de forma estável
no ambiente. A medição anterior (8 perguntas, limiar 0,30) deu recall@5 **0,479**, com o reranker
estourando o timeout e caindo no fallback.

### Calibração do limiar da densa (`RAG_DENSE_THRESHOLD`)

Varredura sobre as 14 perguntas rotuladas e 10 perguntas **sem fonte** na base
(`evals/retrieval_oos.yaml`):

| Limiar | recall@5 | perguntas sem fonte que ainda trazem trecho |
|--------|----------|----------------------------------------------|
| 0,35 – 0,45 | 0,798 | 2/10 |
| 0,475  | 0,798 | 1/10 |
| 0,50 – 0,525 | 0,798 | 0/10 |
| 0,55   | 0,762 | 0/10 |
| 0,60   | 0,488 | 0/10 |

Nenhum limiar de similaridade separa tudo: a comparação curta e legítima "Diferença entre Get
Clássica e Get Smart" tem cosseno máximo **0,437**, enquanto "Como contrato a Get Turbo X?" (produto
inexistente) chega a **0,47–0,49**. Um corte em 0,50 zera o vazamento mas descarta perguntas reais
do enunciado. Escolhido **0,40**: 0,037 de folga abaixo do pior caso legítimo. A recusa do que não
existe fica com as camadas seguintes (abaixo). Amostra pequena (14 + 10 perguntas): o número deve ser
revisto quando o conjunto crescer.

### Camadas que impedem resposta inventada

Como o retrieval deixa passar "Get Turbo X", a defesa é em profundidade:

1. O agente de conhecimento recebe a regra de que um nome/valor citado na pergunta precisa aparecer
   no contexto; do contrário diz que não encontrou, com confiança ≤ 0,2 (o supervisor escala).
2. O grounding do guardrail de saída recebe **a pergunta e o texto das passagens** (não só título e
   URL) e reprova resposta sobre outra coisa que não a perguntada.
3. Uma negativa de capacidade ("não aceita/oferece/possui…") é bloqueada de forma determinística
   quando as passagens não trazem a mesma negativa.

Validação com o modelo real em `docs/reports/smoke.md` (3 perguntas de controle × 5 execuções).

## Consequências

- (+) Padrão mais simples e mais preciso nos dados; sem modelo de 150 MB nem índice BM25 em memória.
- (+) A estratégia híbrida segue implementada e testada, trocável por variável de ambiente.
- (−) Perde casamento lexical exato de nomes de produto (a busca densa as acha pelo significado, com
  cosseno mais baixo em consultas curtas).
- (−) O enunciado cita BM25 + RRF + rerank como pipeline esperado; ele existe e é selecionável, mas
  **não é o padrão**. Se a entrega exigir que ele seja o padrão, basta `RAG_STRATEGY=hybrid_rerank`
  (com o custo de memória e latência descrito acima).
- (−) Recall@5 do conjunto ampliado (0,798) abaixo do gate de 0,90.
- Próximos passos para fechar o gate: ampliar o conjunto rotulado, testar `bge-reranker-v2-m3` em
  hardware com mais memória e migrar o BM25 para `pg_search` em produção.
