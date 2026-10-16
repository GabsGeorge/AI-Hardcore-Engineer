import { useMutation } from "@tanstack/react-query";
import { useEffect } from "react";
import { useTranslation } from "react-i18next";
import { Link, useSearchParams } from "react-router-dom";
import { Alert, Logo, Spinner } from "@/design";
import { api } from "@/lib/api";

export function VerifyPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const mutation = useMutation({
    mutationFn: () => api.post<{ status: "ok" }>("/v1/auth/verify-email", { token }),
  });

  useEffect(() => {
    if (token !== "") {
      mutation.mutate();
    }
    // Intentional: one shot per mount; we don't want to re-fire if the user re-renders.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 p-6 text-center">
      <Logo height={40} />
      <h1 className="text-display text-ink-900">{t("auth.verifyTitle")}</h1>
      {mutation.isPending ? (
        <Spinner />
      ) : mutation.isSuccess ? (
        <Alert tone="success">{t("auth.verifyOk")}</Alert>
      ) : mutation.isError || token === "" ? (
        <Alert tone="danger">{t("auth.verifyFail")}</Alert>
      ) : null}
      <Link to="/login" className="text-label text-brand hover:underline">
        {t("auth.signIn")}
      </Link>
    </main>
  );
}
