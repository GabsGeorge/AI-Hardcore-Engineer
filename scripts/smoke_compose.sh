#!/usr/bin/env bash
#
# Smoke test da CI (REQ-INF-01, REQ-INF-02, REQ-INF-03):
# - clone limpo + .env de teste → docker compose up → /readyz 200
# - imagem final sem gcc/uv e com HEALTHCHECK
# - serviço `tests` do docker-compose.test.yml passa sem rota de saída (rede interna)
#
# Executa idempotente: faz down ao final e em qualquer erro.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

cleanup() {
  docker compose -f docker-compose.yml -f docker-compose.test.yml down -v --remove-orphans >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "::group::env"
if [[ ! -f .env ]]; then
  cp .env.example .env
  # Preenche segredos mínimos para o smoke não exigir chave real:
  python3 - <<'PY'
import secrets, pathlib
p = pathlib.Path(".env")
text = p.read_text()
text = text.replace("JWT_SECRET=", f"JWT_SECRET={secrets.token_hex(32)}")
text = text.replace("POSTGRES_PASSWORD=", f"POSTGRES_PASSWORD={secrets.token_hex(16)}")
text = text.replace("DATABASE_URL=", "DATABASE_URL=postgresql://app:changeme@postgres:5432/app")
text = text.replace("REDIS_URL=", "REDIS_URL=redis://redis:6379/0")
p.write_text(text)
PY
fi
echo "::endgroup::"

echo "::group::build"
docker compose build api
echo "::endgroup::"

echo "::group::image sanity"
# HEALTHCHECK presente
docker inspect --format '{{.Config.Healthcheck.Test}}' $(docker compose config --format json | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['services']['api']['image'])" 2>/dev/null || docker compose images -q api)
# Sem toolchain em runtime
if docker run --rm --entrypoint sh $(docker compose images -q api) -c 'command -v gcc || command -v uv' ; then
  echo "ERRO: gcc/uv presentes na imagem final" >&2
  exit 2
fi
echo "::endgroup::"

echo "::group::up + /readyz"
docker compose up -d
# Aguarda o /readyz (timeout 60 s)
for i in $(seq 1 60); do
  if curl -sfS http://localhost:8000/readyz >/dev/null; then
    echo "readyz OK na iteração $i"
    break
  fi
  sleep 1
  [[ $i -eq 60 ]] && { echo "readyz nunca ficou 200" >&2; exit 3; }
done
echo "::endgroup::"

echo "::group::tests (rede interna)"
docker compose -f docker-compose.yml -f docker-compose.test.yml run --rm tests pytest -q
echo "::endgroup::"

echo "smoke OK"
