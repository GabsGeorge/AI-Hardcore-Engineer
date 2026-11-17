import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import i18n from "i18next";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { beforeAll, beforeEach, describe, expect, it, vi } from "vitest";
import { ChatPage } from "./ChatPage";

type Handlers = {
  onEvent?: (name: string, data: unknown) => void;
  onError?: (err: Error) => void;
  onDone?: () => void;
};

const streamPostMock = vi.fn();
vi.mock("@/lib/sse", () => ({
  streamPost: (...args: unknown[]) => streamPostMock(...args),
}));

function renderPage() {
  return render(
    <MemoryRouter initialEntries={["/chat"]}>
      <Routes>
        <Route path="/chat" element={<ChatPage />} />
        <Route path="/chat/:id" element={<ChatPage />} />
      </Routes>
    </MemoryRouter>,
  );
}

async function ask(text: string) {
  const user = userEvent.setup();
  renderPage();
  await user.type(screen.getByLabelText(/mensagem|message/i), text);
  await user.click(screen.getByRole("button", { name: /enviar|send/i }));
}

const FINAL = {
  response: "A taxa do débito acima de R$ 80 mil é 0,85%.",
  conversation_id: "c1",
  route: ["supervisor", "knowledge"],
  sources: [
    {
      title: "Maquininhas Getnet",
      url: "https://site.getnet.com.br/todas-as-maquininhas/#offers-card",
      kind: "kb",
    },
  ],
  tools_used: [],
  confidence: 0.9,
  handoff: { status: "none", ticket_id: null },
  guardrails: { input: "pass", output: "pass" },
  trace_id: "t1",
};

describe("ChatPage: falhas do fluxo nunca ficam em silêncio", () => {
  // O jsdom reporta en-US e a tela abriria em inglês; os textos verificados aqui são em português.
  beforeAll(async () => {
    await i18n.changeLanguage("pt");
  });
  beforeEach(() => {
    // Sem retornar o mock: o Vitest trata uma função devolvida pelo beforeEach como limpeza.
    streamPostMock.mockReset();
  });

  it("mostra a resposta e a fonte quando o fluxo termina com done", async () => {
    streamPostMock.mockImplementation(async (_path: string, _body: unknown, h: Handlers) => {
      h.onEvent?.("done", FINAL);
    });
    await ask("qual a taxa do débito?");
    expect(await screen.findByText(/0,85%/)).toBeInTheDocument();
    expect(screen.queryByRole("alert")).not.toBeInTheDocument();
  });

  it("avisa quando o fluxo termina sem o evento done", async () => {
    streamPostMock.mockImplementation(async (_path: string, _body: unknown, h: Handlers) => {
      h.onEvent?.("agent_step", { node: "supervisor" });
      h.onDone?.();
    });
    await ask("qual a taxa do débito?");
    expect(await screen.findByRole("alert")).toHaveTextContent(/interrompida/i);
  });

  it("avisa quando a API responde com erro", async () => {
    streamPostMock.mockImplementation(async () => {
      throw new Error("sse_http_500");
    });
    await ask("qual a taxa do débito?");
    expect(await screen.findByRole("alert")).toHaveTextContent(/não consegui responder/i);
  });

  it("não mostra o aviso de erro quando o limite de mensagens é atingido", async () => {
    streamPostMock.mockImplementation(async () => {
      throw new Error("sse_http_429");
    });
    await ask("qual a taxa do débito?");
    expect(await screen.findByText(/muitas mensagens/i)).toBeInTheDocument();
    expect(screen.queryByText(/não consegui responder/i)).not.toBeInTheDocument();
  });
});
