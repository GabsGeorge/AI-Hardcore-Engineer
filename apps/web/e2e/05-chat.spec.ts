import { expect, test, type Page, type Route } from "@playwright/test";

/**
 * Jornada do chat no navegador, com as respostas do servidor simuladas no próprio navegador
 * (`page.route`): sem LLM e sem gastar tokens, então roda no CI. O que se testa é o que o lojista
 * vê: a resposta com a fonte clicável e, principalmente, que uma falha do fluxo nunca fica em
 * silêncio. A resposta real do modelo é validada à parte (docs/reports/smoke.md).
 */

const SOURCE_URL = "https://site.getnet.com.br/todas-as-maquininhas/#offers-card";

const FINAL = {
  response: "A taxa do débito para quem fatura acima de R$ 80 mil é 0,85% [1].",
  conversation_id: "11111111-1111-4111-8111-111111111111",
  route: ["input_guardrail", "supervisor", "knowledge", "synthesize", "output_guardrail"],
  sources: [
    {
      title: "Maquininhas Getnet: taxas por faixa de faturamento",
      url: SOURCE_URL,
      kind: "kb",
      retrieved_at: "2026-11-17T01:57:11+00:00",
    },
  ],
  tools_used: [{ name: "search_knowledge_base", status: "ok", latency_ms: 120 }],
  confidence: 0.9,
  handoff: { status: "none", ticket_id: null },
  guardrails: { input: "pass", output: "pass" },
  trace_id: "0123456789abcdef0123456789abcdef",
};

function sse(events: [string, unknown][]): string {
  // O Starlette envia CRLF entre eventos; o cliente precisa entender os dois.
  return events
    .map(([name, data]) => `event: ${name}\r\ndata: ${JSON.stringify(data)}\r\n\r\n`)
    .join("");
}

// O design system mantém um role="alert" invisível e sempre presente (anúncios para leitores de
// tela); um aviso de verdade é o alerta que tem texto.
const visibleAlert = (page: Page) => page.getByRole("alert").filter({ hasText: /./ });

async function asMerchant(page: Page, onChat: (route: Route) => Promise<void>) {
  await page.route("**/v1/auth/me", (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ id: "cliente1988", role: "merchant", display_name: "Loja Demo" }),
    }),
  );
  await page.route("**/v1/chat/stream", onChat);
  await page.goto("/chat");
}

async function ask(page: Page, text: string) {
  await page.getByLabel(/^mensagem/i).fill(text);
  await page.getByRole("button", { name: /^enviar$/i }).click();
}

test.describe("Chat — o que o lojista vê", () => {
  test("mostra a resposta e a fonte clicável", async ({ page }) => {
    await asMerchant(page, (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sse([
          ["agent_step", { node: "supervisor" }],
          ["agent_step", { node: "knowledge" }],
          ["done", FINAL],
        ]),
      }),
    );
    await ask(page, "Qual a taxa do débito acima de 80 mil?");

    // A lista de mensagens (role="log"): o anúncio para leitores de tela repete o texto fora dela.
    await expect(page.getByRole("log").getByText(/0,85%/)).toBeVisible();
    const source = page.getByRole("link", { name: /Maquininhas Getnet/ });
    await expect(source).toHaveAttribute("href", SOURCE_URL);
    await expect(source).toHaveAttribute("target", "_blank");
    await expect(source).toHaveAttribute("rel", /noopener/);
    await expect(visibleAlert(page)).toHaveCount(0);
  });

  test("avisa quando o fluxo é cortado antes do evento final", async ({ page }) => {
    await asMerchant(page, (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sse([["agent_step", { node: "supervisor" }]]),
      }),
    );
    await ask(page, "Qual a taxa do débito?");

    await expect(visibleAlert(page)).toContainText(/interrompida/i);
    await expect(page.getByLabel(/^mensagem/i)).toBeEnabled();
  });

  test("avisa quando a API responde com erro", async ({ page }) => {
    await asMerchant(page, (route) =>
      route.fulfill({ status: 500, contentType: "application/json", body: "{}" }),
    );
    await ask(page, "Qual a taxa do débito?");

    await expect(visibleAlert(page)).toContainText(/não consegui responder/i);
    await expect(page.getByLabel(/^mensagem/i)).toBeEnabled();
  });

  test("avisa o limite de mensagens sem tratar como erro de resposta", async ({ page }) => {
    await asMerchant(page, (route) =>
      route.fulfill({ status: 429, contentType: "application/json", body: "{}" }),
    );
    await ask(page, "Qual a taxa do débito?");

    await expect(page.getByText(/muitas mensagens/i)).toBeVisible();
    await expect(page.getByText(/não consegui responder/i)).toHaveCount(0);
  });

  test("mostra a fila de atendimento e trava o campo quando escala para um humano", async ({
    page,
  }) => {
    const handoff = { status: "awaiting_human", ticket_id: "T-1042" };
    await asMerchant(page, (route) =>
      route.fulfill({
        status: 200,
        contentType: "text/event-stream",
        body: sse([
          ["handoff", handoff],
          ["done", { ...FINAL, response: "", sources: [], handoff }],
        ]),
      }),
    );
    await ask(page, "Quero falar com um atendente");

    await expect(page.getByText(/aguardando atendente/i).first()).toBeVisible();
    await expect(page.getByLabel(/^mensagem/i)).toBeDisabled();
    await expect(visibleAlert(page)).toHaveCount(0);
  });
});
