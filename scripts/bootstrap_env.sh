#!/usr/bin/env bash
# Preenche .env com segredos aleatorios para primeiro uso. Nao sobrescreve variaveis
# ja preenchidas (openai etc). Idempotente.
#
# Uso:
#   cp .env.example .env
#   ./scripts/bootstrap_env.sh
#   # abra o .env e preencha OPENAI_API_KEY — o resto ja esta pronto para docker compose up -d
set -euo pipefail

ENV_FILE="${ENV_FILE:-.env}"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "erro: $ENV_FILE nao existe. Rode 'cp .env.example .env' primeiro." >&2
  exit 1
fi

# Gera um segredo com `openssl rand`. Fallbacks: /dev/urandom via base64, python.
rand_secret() {
  local bytes="${1:-32}"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -hex "$bytes"
  elif command -v python3 >/dev/null 2>&1; then
    python3 -c "import secrets; print(secrets.token_hex($bytes))"
  else
    head -c $((bytes * 2)) /dev/urandom | od -An -tx1 | tr -d ' \n'
  fi
}

rand_password() {
  local len="${1:-32}"
  if command -v openssl >/dev/null 2>&1; then
    openssl rand -base64 48 | tr -d '/+=\n' | head -c "$len"
  else
    rand_secret 24 | head -c "$len"
  fi
}

# Preenche a VAR com VALUE em $ENV_FILE **apenas se** a linha estiver vazia (VAR=).
# Se VAR nao existir no arquivo, acrescenta no fim.
fill_if_empty() {
  local var="$1" value="$2"
  local line
  if ! grep -q "^${var}=" "$ENV_FILE"; then
    printf '%s=%s\n' "$var" "$value" >> "$ENV_FILE"
    echo "ok: $var acrescentado"
    return
  fi
  line="$(grep "^${var}=" "$ENV_FILE" | head -1)"
  if [[ "$line" == "${var}=" ]]; then
    local tmp
    tmp="$(mktemp)"
    awk -v v="$var" -v val="$value" '
      $0 ~ "^"v"=$" { print v"="val; next }
      { print }
    ' "$ENV_FILE" > "$tmp"
    mv "$tmp" "$ENV_FILE"
    echo "ok: $var preenchido"
  else
    echo "skip: $var ja definido"
  fi
}

# Segredos de app
fill_if_empty JWT_SECRET          "$(rand_secret 32)"
fill_if_empty POSTGRES_PASSWORD   "$(rand_password 24)"
fill_if_empty SESSION_SECRET      "$(rand_secret 32)"
fill_if_empty PASSWORD_PEPPER     "$(rand_secret 32)"

# Senha do admin seed e do Grafana (profile obs)
fill_if_empty ADMIN_SEED_PASSWORD "$(rand_password 20)"
fill_if_empty GRAFANA_ADMIN_PASSWORD "$(rand_password 32)"

echo
echo "Pronto. Agora preencha OPENAI_API_KEY no $ENV_FILE e rode: docker compose up -d --build"
