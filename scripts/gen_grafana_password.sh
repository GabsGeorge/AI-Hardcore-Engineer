#!/usr/bin/env bash
# Gera uma senha forte para o admin do Grafana e injeta em .env.
#
# Uso:
#   ./scripts/gen_grafana_password.sh         # grava em .env, imprime no stdout
#   ./scripts/gen_grafana_password.sh --print # so imprime, nao mexe no .env
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"
PASS="$(openssl rand -base64 24 | tr -d '/+=\n' | head -c 32)"

if [[ "${1:-}" == "--print" ]]; then
  echo "$PASS"
  exit 0
fi

if [[ ! -f "$ENV_FILE" ]]; then
  echo "erro: $ENV_FILE nao existe. Rode 'cp .env.example .env' primeiro." >&2
  exit 1
fi

# Substitui ou acrescenta a linha GRAFANA_ADMIN_PASSWORD=... in-place.
if grep -q '^GRAFANA_ADMIN_PASSWORD=' "$ENV_FILE"; then
  # sed -i tem sintaxe diferente em BSD (mac) vs GNU; o awk abaixo e portatil.
  tmp="$(mktemp)"
  awk -v p="$PASS" '/^GRAFANA_ADMIN_PASSWORD=/{print "GRAFANA_ADMIN_PASSWORD="p; next} {print}' "$ENV_FILE" > "$tmp"
  mv "$tmp" "$ENV_FILE"
else
  echo "GRAFANA_ADMIN_PASSWORD=$PASS" >> "$ENV_FILE"
fi

echo "ok: GRAFANA_ADMIN_PASSWORD gravado em $ENV_FILE"
echo "senha (anote agora, nao e exibida de novo):"
echo "  $PASS"
