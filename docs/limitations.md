# Limitações aceitas (`shortcut:`) e trade-offs (T178)

Nesta entrega, três decisões conscientes trocam robustez máxima por simplicidade/custo.
Cada item lista **onde**, **o que** e **o caminho de evolução**.

---

## 1. Rate limit em janela fixa (processo-local)

- **Onde**: [src/app/api/limits.py](../src/app/api/limits.py)
- **O que**: contador por `user_id` com `INCR` + `EXPIRE` em Redis, janela fixa de 60 s.
- **Consequência**: na troca de minuto, um lojista pode disparar **até 2× o limite em uma
  janela deslizante de 60 s** (as duas pontas do minuto).
- **Risco aceito**: baixo. O limite por si só é defensivo, não contratual, e o perfil de uso
  pessoa-máquina não aproveita essa borda.
- **Evolução**: trocar por "sliding window log" ou "token bucket" quando o tráfego crescer.
  A interface do módulo não muda — só a implementação de `check_rate_limit`.

## 2. Circuit breaker in-process

- **Onde**: [src/app/core/resilience.py](../src/app/core/resilience.py), aplicado ao DuckDuckGo
  em [knowledge_tools.py](../src/app/tools/knowledge_tools.py).
- **O que**: estado do breaker vive por processo (dict em memória, protegido por `asyncio.Lock`).
- **Consequência**: num cluster multi-réplica, cada réplica "aprende" o estado da dependência
  separadamente — a quinta falha seguida de **cada** réplica abre o circuito dela, não o global.
- **Risco aceito**: baixo para o volume atual. Com o circuito aberto, o web_search devolve lista
  vazia e o Knowledge responde só com a base interna.
- **Fora do breaker, por decisão**: o LLM já tem `max_retries` e o modelo de fallback
  (`OPENAI_MODEL_FALLBACK`); um breaker na frente só trocaria uma resposta degradada por outra.
  O reranker (FlashRank) roda em processo, sem rede, então não há dependência para isolar.
- **Evolução**: mover para Redis com chaves por `cb:{service}` + `SET NX EX` quando houver
  mais de uma réplica em produção. A API pública (`get_breaker`, `with_circuit_breaker`) fica
  igual.

## 3. Chunker baseado em palavras

- **Onde**: [src/app/rag/chunking.py](../src/app/rag/chunking.py)
- **O que**: contamos palavras separadas por whitespace como aproximação de tokens.
- **Consequência**: o tamanho real do chunk em tokens varia (PT ~1.3 tokens/palavra, EN ~1.0),
  então o teto efetivo oscila. Ainda assim fica dentro do limite do embedding model.
- **Risco aceito**: baixo. Para `text-embedding-3-small` (8191 tokens), a margem é folgada.
- **Evolução**: trocar por `tiktoken` quando o perfil de documento ficar mais longo (ou mudar
  para outro embedding com limite menor).

---

## O que NÃO é shortcut

- **Identidade** (`user_id`): nunca vem do payload, só do JWT (`sub`), via `config["configurable"]`.
  Isso é regra dura — vide [ADR 0005](adr/0005-identidade-via-token.md).
- **PII**: `mask()` roda antes de qualquer LLM/log/checkpoint; re-máscara no output. Teste
  dedicado em `tests/security/test_pii.py`.
- **HITL**: `interrupt()` + `Command(resume=...)` **na mesma thread** e com a identidade do
  dono do ticket. Ver [ADR 0004](adr/0004-hitl-interrupt.md).
- **Retrieval híbrido**: BM25 + densa + RRF + rerank são obrigatórios no caminho principal
  (não há "shortcut" aqui). Ver [ADR 0003](adr/0003-busca-hibrida.md).
