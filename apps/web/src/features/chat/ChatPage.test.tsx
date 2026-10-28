import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ChatPage } from "./ChatPage";

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

describe("ChatPage", () => {
  it("renderiza input, botão de envio e começa desabilitado", () => {
    renderPage();
    const input = screen.getByLabelText(/mensagem|message/i);
    expect(input).toBeInTheDocument();
    const sendButton = screen.getByRole("button", { name: /enviar|send/i });
    expect(sendButton).toBeDisabled();
  });

  it("habilita envio depois que o usuário digita e dispara streamPost", async () => {
    streamPostMock.mockImplementation(async () => {
      // Simula um stream que completa imediatamente sem emitir eventos.
    });
    const user = userEvent.setup();
    renderPage();
    const input = screen.getByLabelText(/mensagem|message/i);
    await user.type(input, "oi");
    const sendButton = screen.getByRole("button", { name: /enviar|send/i });
    expect(sendButton).toBeEnabled();
    await user.click(sendButton);
    expect(streamPostMock).toHaveBeenCalledTimes(1);
    expect(streamPostMock).toHaveBeenCalledWith(
      "/v1/chat/stream",
      expect.objectContaining({ message: "oi" }),
      expect.anything(),
      expect.anything(),
    );
  });
});
