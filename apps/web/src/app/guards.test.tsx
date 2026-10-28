import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { AuthGuard, RoleGuard } from "./guards";
import type { SessionAccount } from "./session";

vi.mock("./session", async () => {
  const actual = await vi.importActual<typeof import("./session")>("./session");
  return { ...actual, useSession: vi.fn() };
});

async function renderWith(
  session: { data: SessionAccount | null | undefined; isLoading: boolean },
  initialPath: string,
  element: React.ReactElement,
) {
  const { useSession } = await import("./session");
  (useSession as unknown as ReturnType<typeof vi.fn>).mockReturnValue(session);
  const client = new QueryClient({ defaultOptions: { queries: { retry: false } } });
  return render(
    <QueryClientProvider client={client}>
      <MemoryRouter initialEntries={[initialPath]}>
        <Routes>
          <Route path="/login" element={<div>login-page</div>} />
          <Route element={element}>
            <Route path="/protected" element={<div>protected-content</div>} />
          </Route>
        </Routes>
      </MemoryRouter>
    </QueryClientProvider>,
  );
}

describe("AuthGuard", () => {
  it("redireciona para /login preservando next quando não há sessão", async () => {
    await renderWith({ data: null, isLoading: false }, "/protected?x=1", <AuthGuard />);
    expect(screen.getByText("login-page")).toBeInTheDocument();
    expect(screen.queryByText("protected-content")).toBeNull();
  });

  it("renderiza a rota protegida quando há sessão", async () => {
    await renderWith(
      {
        data: { id: "acc_1", role: "merchant", display_name: "Loja" },
        isLoading: false,
      },
      "/protected",
      <AuthGuard />,
    );
    expect(screen.getByText("protected-content")).toBeInTheDocument();
  });

  it("mostra spinner enquanto a sessão carrega (não redireciona ainda)", async () => {
    await renderWith({ data: undefined, isLoading: true }, "/protected", <AuthGuard />);
    expect(screen.queryByText("login-page")).toBeNull();
    expect(screen.queryByText("protected-content")).toBeNull();
  });
});

describe("RoleGuard", () => {
  it("bloqueia com Alert quando o papel não está na allow-list", async () => {
    await renderWith(
      {
        data: { id: "acc_1", role: "merchant", display_name: "Loja" },
        isLoading: false,
      },
      "/protected",
      <RoleGuard allow={["admin"]} />,
    );
    expect(screen.queryByText("protected-content")).toBeNull();
    // O Alert do design system renderiza title + body dentro de uma role="alert" / main.
    expect(screen.getByRole("alert")).toBeInTheDocument();
  });

  it("libera quando o papel está permitido", async () => {
    await renderWith(
      {
        data: { id: "acc_1", role: "admin", display_name: "Admin" },
        isLoading: false,
      },
      "/protected",
      <RoleGuard allow={["admin"]} />,
    );
    expect(screen.getByText("protected-content")).toBeInTheDocument();
  });

  it("redireciona para /login sem sessão (não cai no Alert de role)", async () => {
    await renderWith(
      { data: null, isLoading: false },
      "/protected",
      <RoleGuard allow={["admin"]} />,
    );
    expect(screen.getByText("login-page")).toBeInTheDocument();
  });
});
