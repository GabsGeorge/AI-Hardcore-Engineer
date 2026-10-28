# Teste de carga — `/v1/chat` (REQ-REL-04)

**Cenário**: 20 VUs em `/v1/chat`, mix 70/30 simples/composto, duração 2 min, com fakes de
LLM determinísticos nos cenários reproducíveis em laboratório.

## Rodar localmente

O rate limit do `/v1/chat` é 30 req/min por usuário (REQ-SEC-08). Para 20 VUs em paralelo
sem saturar, cada VU usa seu próprio token — passe uma lista separada por vírgula em
`AUTH_TOKENS`. Com só um token em `AUTH_TOKEN`, a corrida é válida mas as iterações
batem no rate limit e viram 429.

```bash
cp .env.example .env
docker compose up -d --build api
# Seed 20 usuarios de carga + emissao dos tokens:
docker compose exec api python -c "
import asyncio
from app.db.pool import get_pool, open_pool
from app.core.config import get_settings
async def main():
    await open_pool(get_settings().database_url)
    async with get_pool().connection() as c:
        for i in range(1, 21):
            uid = f'k6user{i:02d}'
            await c.execute(\"INSERT INTO users (id, role, display_name) VALUES (%s, 'merchant', %s) ON CONFLICT (id) DO NOTHING\", (uid, f'K6 User {i:02d}'))
asyncio.run(main())
"
TOKENS=""
for i in $(seq -w 1 20); do
  T=$(docker compose exec -T api python scripts/issue_token.py "k6user${i}" --role merchant | tail -1)
  TOKENS="${TOKENS}${TOKENS:+,}${T}"
done
docker compose --profile load run --rm -e AUTH_TOKENS="${TOKENS}" k6 run /scripts/chat.js
```

Thresholds de bloqueio (ver `deploy/k6/chat.js`):

| cenário          | métrica            | alvo        |
|------------------|--------------------|-------------|
| simples          | p(95) duração      | **< 8 s**   |
| composto         | p(95) duração      | **< 15 s**  |
| global           | taxa de erro HTTP  | **< 1 %**   |

## Como ler o resultado

- O k6 encerra com código ≠ 0 se qualquer threshold estourar — o CI falha.
- O resumo final sai no stdout; para arquivo use `--out json=load.json`.
- Com o profile `obs` ativo, o Grafana (`dashboards/operational.json`) mostra a mesma
  distribuição de latência pelas labels `getnet_http_request_duration_seconds`.

## Último run

**Quando**: 2026-10-28 15:57 UTC · **Host**: desenvolvedor local (Windows 10, Docker Desktop)
**Stack**: `docker compose up -d api postgres redis mailpit` sem profile `obs`, dummy
`OPENAI_API_KEY` (todas as respostas via `degraded_response`, retriever `index: empty` —
mesmo assim o pipeline inteiro é exercitado: auth, guardrails, rate limit, idempotência,
supervisor e route). Carga: 20 VUs × 2 min, 1 req/s por VU, 70/30 simples/composto.

| Métrica                                | Observado   | Threshold   | Resultado |
|---------------------------------------|-------------|-------------|-----------|
| `http_req_duration{scenario:simple}` p95   | **2.42 s**  | < 8 s       | ✅        |
| `http_req_duration{scenario:compound}` p95 | **2.96 s**  | < 15 s      | ✅        |
| `http_req_failed` rate                    | **0.00%**   | < 1 %       | ✅        |

**Resumo** (saída do k6):

```
checks_total.......: 800    6.579707/s
checks_succeeded...: 100.00% 800 out of 800
checks_failed......: 0.00%   0 out of 800
http_req_duration..............: avg=2.03s med=1.92s p(90)=2.13s p(95)=2.52s max=5.02s
http_req_failed................: 0.00%  0 out of 800
http_reqs......................: 800    6.579707/s
iterations.....................: 800    6.579707/s
```

### Interpretação

- Latência média de 2.03 s é consistente com o custo do grafo (supervisor → especialista
  → síntese) rodando em CPU com embeddings dummy; a cauda em 5 s vem de duas iterações
  isoladas (jitter do GIL + bloqueio momentâneo do pool pg).
- Zero erros com 20 tokens distintos confirma que o rate limit por usuário (30/min)
  acomoda o padrão esperado (um lojista fazendo poucas perguntas por minuto). Com um
  único token em `AUTH_TOKEN` o teste bate em 429 após ~30 requests, o que é o
  comportamento desejado — ver seção "Rodar localmente".
- Com modelo real da OpenAI (gpt-4o-mini) a latência deve subir ~2–4 s por iteração;
  o SLO p95 de 8 s dá folga para isso.
- Com retriever populado (ingest ok) o `supervisor` passa a chamar `knowledge`/`policy`
  em vez de cair direto no `degraded_response`; o teste de regressão será rodar o mesmo
  cenário contra uma stack com `OPENAI_API_KEY` real e comparar p95.

### Histórico

| Data       | p95 simples | p95 composto | Erro | Observação                                    |
|------------|-------------|--------------|------|-----------------------------------------------|
| 2026-10-28 | 2.42 s      | 2.96 s       | 0 %  | Primeira execução oficial, dummy key, degraded |
