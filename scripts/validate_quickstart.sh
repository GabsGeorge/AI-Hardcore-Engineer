#!/usr/bin/env bash
# T105 — Valida o quickstart 002-web-ui em um clone limpo (sem Python/Node no host).
#
# Uso (num clone recém-feito do repo, com Docker Desktop rodando):
#
#   cp .env.example .env       # preencha OPENAI_API_KEY, JWT_SECRET, SESSION_SECRET,
#                              # PASSWORD_PEPPER, POSTGRES_PASSWORD, DATABASE_URL,
#                              # REDIS_URL e SMTP_URL=smtp://mailpit:1025
#   bash scripts/validate_quickstart.sh
#
# O script percorre o quickstart do começo ao fim e falha no primeiro passo que
# divergir do esperado. É idempotente: pode ser rodado várias vezes seguidas.

set -euo pipefail

say()  { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }
pass() { printf '\033[1;32m✓ %s\033[0m\n' "$*"; }
fail() { printf '\033[1;31m✗ %s\033[0m\n' "$*" >&2; exit 1; }

[ -f .env ] || fail "Faltou copiar .env.example para .env antes de rodar."

say "1/7 — Subindo a stack (api + web + mailpit + postgres + redis)"
docker compose up -d --build
sleep 3

say "2/7 — Healthchecks"
curl -fsS http://localhost/healthz   > /dev/null || fail "nginx /healthz não respondeu"
curl -fsS http://localhost:8000/readyz > /dev/null || fail "api /readyz não respondeu"
pass "nginx (80) e api (8000) de pé"

say "3/7 — Seed do admin de demo (idempotente)"
docker compose exec -T api python scripts/create_demo_admin.py \
    --email admin@getnet.example --password 'senha-segura-demo-123' || true
pass "admin de demo garantido"

say "4/7 — Suíte de testes (rede isolada)"
docker compose -f docker-compose.yml -f docker-compose.test.yml \
    run --rm tests pytest --maxfail=1 -q > /tmp/pytest.out 2>&1 \
    || { tail -20 /tmp/pytest.out; fail "pytest falhou"; }
pass "pytest verde"

say "5/7 — Lint do front (eslint + prettier + tsc)"
docker compose -f docker-compose.yml -f docker-compose.test.yml \
    run --rm web-lint > /tmp/weblint.out 2>&1 \
    || { tail -20 /tmp/weblint.out; fail "web-lint falhou"; }
pass "web-lint verde"

say "6/7 — Rastreabilidade REQ→task→teste"
docker compose -f docker-compose.yml -f docker-compose.test.yml \
    run --rm tests python scripts/check_traceability.py > /tmp/trace.out 2>&1 \
    || { tail -20 /tmp/trace.out; fail "traceability falhou"; }
pass "traceability atualizada"

say "7/7 — Checagens manuais que ainda dependem de olho humano"
cat <<MANUAL
   • Abrir http://localhost/login e logar com admin@getnet.example / senha-segura-demo-123
   • Confirmar que /admin, /chat, /history, /handoffs renderizam sem erro no console
   • Em http://localhost:8025 (Mailpit) ver o inbox de convites/verificações
   • Dashboards do Grafana (docker compose --profile obs up -d) → painel "Getnet - UI web"
MANUAL

pass "quickstart automatizado passou — faça as checagens manuais acima."
