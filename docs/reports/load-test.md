# Teste de carga — `/v1/chat` (REQ-REL-04)

**Cenário**: 20 VUs em `/v1/chat`, mix 70/30 simples/composto, duração 2 min, com fakes de
LLM determinísticos nos cenários reproducíveis em laboratório.

## Rodar localmente

```bash
cp .env.example .env
# gere um token para o lojista teste:
export K6_AUTH_TOKEN=$(docker compose run --rm api python scripts/issue_token.py cliente1988 --role merchant)
docker compose up -d --build
docker compose --profile load run --rm k6 run /scripts/chat.js
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

> **Estado**: a ser preenchido na primeira execução oficial da entrega.
> O comando acima é determinístico com o `.env.example` + token local; o resultado deste
> arquivo deve ser atualizado quando a stack real roda, substituindo esta nota pela saída
> resumida (checks, http_req_duration e thresholds).
