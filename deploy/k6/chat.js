// Carga sintética para /v1/chat (REQ-REL-04). 20 VUs, mix simples/composto.
//
// Thresholds que FAZEM o k6 sair com erro:
//   - p(95) < 8000 ms  → SLO respondido
//   - p(95) na pergunta composta < 15000 ms
//   - erros HTTP < 1%
//
// Rodar:
//   docker compose --profile load up -d --build k6
//   docker compose run --rm k6 run /scripts/chat.js
import http from "k6/http";
import { check, sleep } from "k6";

const BASE_URL = __ENV.BASE_URL || "http://api:8000";
const TOKEN = __ENV.AUTH_TOKEN || "";

export const options = {
  vus: Number(__ENV.VUS || 20),
  duration: __ENV.DURATION || "2m",
  thresholds: {
    "http_req_duration{scenario:simple}": ["p(95)<8000"],
    "http_req_duration{scenario:compound}": ["p(95)<15000"],
    http_req_failed: ["rate<0.01"],
  },
};

const QUESTIONS_SIMPLE = [
  "Como funciona a antecipação?",
  "Quais as taxas do Pix?",
  "O que é a Get Smart?",
  "Como gero um link de pagamento?",
];
const QUESTIONS_COMPOUND = [
  "Minha máquina não conecta e como funciona a antecipação?",
  "Quando cai a venda de ontem e qual é a taxa de antecipação?",
];

function pick(arr) {
  return arr[Math.floor(Math.random() * arr.length)];
}

export default function () {
  const headers = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${TOKEN}`,
  };
  const scenario = Math.random() < 0.7 ? "simple" : "compound";
  const message =
    scenario === "simple" ? pick(QUESTIONS_SIMPLE) : pick(QUESTIONS_COMPOUND);
  const res = http.post(
    `${BASE_URL}/v1/chat`,
    JSON.stringify({ message }),
    { headers, tags: { scenario } },
  );
  check(res, { "status is 200": (r) => r.status === 200 });
  sleep(1);
}
