import { useQueryClient } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { NavLink, Outlet, useNavigate } from "react-router-dom";
import { Avatar, Button, Logo } from "@/design";
import { api, isApiError } from "@/lib/api";
import { setLanguage, type Language } from "@/lib/i18n";
import { useSession, type Role } from "./session";

const linksByRole: Record<Role, Array<{ to: string; key: "chat" | "history" | "queue" | "admin" | "privacy" }>> = {
  merchant: [
    { to: "/chat", key: "chat" },
    { to: "/history", key: "history" },
    { to: "/privacy", key: "privacy" },
  ],
  operator: [{ to: "/queue", key: "queue" }],
  admin: [
    { to: "/queue", key: "queue" },
    { to: "/admin", key: "admin" },
  ],
};

export function AppLayout() {
  const { t, i18n } = useTranslation();
  const session = useSession();
  const navigate = useNavigate();
  const client = useQueryClient();
  const account = session.data ?? null;

  async function signOut() {
    try {
      await api.post("/v1/auth/logout");
    } catch (err) {
      if (!isApiError(err)) {
        throw err;
      }
    }
    client.setQueryData(["session"], null);
    navigate("/login", { replace: true });
  }

  const otherLang: Language = i18n.language === "pt" ? "en" : "pt";

  return (
    <div className="flex min-h-screen flex-col bg-page text-ink-700">
      <header className="border-b border-line bg-surface-100">
        <div className="mx-auto flex max-w-6xl items-center justify-between gap-4 px-4 py-3 sm:px-8">
          <div className="flex items-center gap-6">
            <Logo />
            <nav aria-label="Principal" className="hidden gap-4 sm:flex">
              {(account !== null ? linksByRole[account.role] : []).map((link) => (
                <NavLink
                  key={link.to}
                  to={link.to}
                  className={({ isActive }) =>
                    `text-label ${isActive ? "text-brand" : "text-ink-500 hover:text-ink-700"}`
                  }
                >
                  {t(`nav.${link.key}`)}
                </NavLink>
              ))}
            </nav>
          </div>
          <div className="flex items-center gap-3">
            <button
              onClick={() => setLanguage(otherLang)}
              className="text-label text-ink-500 hover:text-ink-700"
            >
              {otherLang.toUpperCase()}
            </button>
            {account !== null ? (
              <>
                <Avatar name={account.display_name} />
                <span className="hidden text-label text-ink-500 sm:inline">
                  {account.display_name}
                </span>
                <Button intent="ghost" size="sm" onClick={() => void signOut()}>
                  {t("app.signOut")}
                </Button>
              </>
            ) : null}
          </div>
        </div>
      </header>
      <main className="mx-auto w-full max-w-6xl flex-1 px-4 py-6 sm:px-8">
        <Outlet />
      </main>
    </div>
  );
}
