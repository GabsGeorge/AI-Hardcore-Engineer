import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Alert, Spinner } from "@/design";
import { useSession, type Role } from "./session";

export function AuthGuard() {
  const { t } = useTranslation();
  const session = useSession();
  const location = useLocation();
  if (session.isLoading) {
    return <CenteredSpinner label={t("app.loading")} />;
  }
  if (session.data === null) {
    const next = `${location.pathname}${location.search}`;
    return <Navigate to={`/login?next=${encodeURIComponent(next)}`} replace />;
  }
  return <Outlet />;
}

export function RoleGuard({ allow }: { allow: Role[] }) {
  const { t } = useTranslation();
  const session = useSession();
  if (session.isLoading) {
    return <CenteredSpinner label={t("app.loading")} />;
  }
  if (session.data === null) {
    return <Navigate to="/login" replace />;
  }
  if (!allow.includes(session.data.role)) {
    return (
      <main className="mx-auto max-w-md p-8">
        <Alert tone="danger" title={t("accessDenied.title")}>
          {t("accessDenied.body")}
        </Alert>
      </main>
    );
  }
  return <Outlet />;
}

function CenteredSpinner({ label }: { label: string }) {
  return (
    <div className="flex min-h-screen items-center justify-center text-ink-500">
      <div className="flex items-center gap-2">
        <Spinner />
        <span>{label}</span>
      </div>
    </div>
  );
}
