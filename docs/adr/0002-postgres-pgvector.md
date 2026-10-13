# ADR 0002: Postgres 16 + pgvector para tudo

- **Status**: Aceito · **Data**: 2026-10-13 · **Requisitos**: REQ-ORC-06, REQ-RAG-02, REQ-INF-01

## Contexto

Precisamos de vetores, busca lexical, checkpoints do LangGraph, tickets, auditoria, feedback e
dados mock. Um serviço por necessidade (ex.: Chroma + SQLite + Mongo) multiplica as peças.

## Decisão

Um Postgres 16 com `pgvector` (HNSW); o BM25 é um índice em memória montado a partir da tabela
`chunks` (ADR 0003). Checkpointer
`AsyncPostgresSaver` no mesmo banco. Acesso com `psycopg` 3 e SQL explícito; migrações `.sql`.

## Alternativas

- **Chroma/Qdrant + banco relacional**: vetor mais especializado, porém mais um serviço, sem
  transação entre ticket e checkpoint.
- **SQLAlchemy + Alembic**: camada extra para ~12 tabelas simples.

## Consequências

- (+) Um serviço, backups e transações únicos; compose mais leve.
- (−) Busca vetorial menos especializada; o BM25 fica fora do banco, em memória na API (ver
  ADR 0003, com ParadeDB `pg_search` como caminho de produção).
