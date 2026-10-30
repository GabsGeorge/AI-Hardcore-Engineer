#!/usr/bin/env bash
# Roda os 10 cenarios do enunciado contra a API local e salva as respostas cruas em
# $OUT/sc{01..10}.json. Depois monta um resumo em $OUT/summary.txt.
#
# Uso: ./scripts/smoke_scenarios.sh
set -euo pipefail

API="${API:-http://localhost:8000}"
OUT="${OUT:-/tmp/smoke}"
USER_ID="cliente1988"

mkdir -p "$OUT"
TOKEN="$(docker compose exec -T api python scripts/issue_token.py "$USER_ID" --role merchant | tr -d '\r\n')"

make_body() {
  local message="$1" out="$2"
  docker compose exec -T api python -c '
import json, sys
print(json.dumps({"message": sys.argv[1], "user_id": sys.argv[2]}, ensure_ascii=False))
' "$message" "$USER_ID" > "$out"
}

summarize() {
  local id="$1" ms="$2" path="$3"
  # path is on host; copy into api container for python processing
  docker compose cp -q "$path" api:/tmp/sc.json 2>/dev/null || cat "$path" | docker compose exec -T api sh -c "cat > /tmp/sc.json"
  docker compose exec -T api python -c '
import json, sys
sid, ms = sys.argv[1], int(sys.argv[2])
d = json.load(open("/tmp/sc.json", encoding="utf-8"))
route = d.get("route")
handoff = (d.get("handoff") or {}).get("status")
tools = [t.get("name") for t in (d.get("tools_used") or [])]
tool_statuses = [t.get("status") for t in (d.get("tools_used") or [])]
guardrails = d.get("guardrails")
resp = d.get("response") or ""
trace = d.get("trace_id", "")
print(f"sc{sid} ms={ms} route={route} handoff={handoff} tools={tools} statuses={tool_statuses} guardrails={guardrails} resp_len={len(resp)} trace={trace[:12]}")
' "$id" "$ms"
}

run() {
  local id="$1" message="$2"
  local body_file="$OUT/sc${id}.body.json" out="$OUT/sc${id}.json"
  make_body "$message" "$body_file"
  local started ended ms
  started=$(date +%s%3N)
  curl -sS -X POST "$API/v1/chat" \
    -H "Authorization: Bearer $TOKEN" \
    -H "Content-Type: application/json; charset=utf-8" \
    --data-binary @"$body_file" > "$out"
  ended=$(date +%s%3N)
  ms=$((ended - started))
  summarize "$id" "$ms" "$out"
}

{
  run 01 "Diferença entre Get Clássica e Get Smart"
  run 02 "Previsão do tempo em Porto Alegre amanhã"
  run 03 "Quando cai o dinheiro das vendas de ontem?"
  run 04 "Preciso de conta bancária para receber via Pix?"
  run 05 "Minha máquina não conecta à internet, o que faço?"
  run 06 "Como funciona a antecipação de recebíveis?"
  run 07 "Cotação do euro hoje"
  run 08 "Minha máquina mostrou erro de transação recusada, por quê?"
  run 09 "Como funcionam as parcelas no crediário?"
  run 10 "Como vender pelo WhatsApp com Link de Pagamento?"
} 2>&1 | tee "$OUT/summary.txt"

echo
echo "pronto. Respostas em $OUT/sc{01..10}.json; resumo em $OUT/summary.txt."
