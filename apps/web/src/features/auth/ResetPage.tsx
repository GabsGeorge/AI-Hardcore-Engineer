import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, Navigate, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";
import { Alert, Button, FormField, Logo, PasswordInput } from "@/design";
import { api, isApiError } from "@/lib/api";

const Schema = z.object({ new_password: z.string().min(12).max(256) });

export function ResetPage() {
  const { t } = useTranslation();
  const [params] = useSearchParams();
  const navigate = useNavigate();
  const token = params.get("token") ?? "";
  const [password, setPassword] = useState("");
  const [weak, setWeak] = useState(false);
  const [tokenInvalid, setTokenInvalid] = useState(false);

  const mutation = useMutation({
    mutationFn: (body: { token: string; new_password: string }) =>
      api.post<{ status: "ok" }>("/v1/auth/password/reset", body),
    onError: (err) => {
      if (isApiError(err) && err.code === "token_invalid") {
        setTokenInvalid(true);
      } else if (isApiError(err) && err.code === "weak_password") {
        setWeak(true);
      }
    },
    onSuccess: () => navigate("/login", { replace: true }),
  });

  if (token === "") {
    return <Navigate to="/forgot" replace />;
  }

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = Schema.safeParse({ new_password: password });
    if (!parsed.success) {
      setWeak(true);
      return;
    }
    setWeak(false);
    setTokenInvalid(false);
    mutation.mutate({ token, new_password: password });
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 p-6">
      <header className="flex flex-col items-center gap-3 text-center">
        <Logo height={40} />
        <h1 className="text-display text-ink-900">{t("auth.resetTitle")}</h1>
      </header>
      {tokenInvalid ? <Alert tone="danger">{t("auth.verifyFail")}</Alert> : null}
      <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
        <FormField
          label={t("auth.newPassword")}
          required
          help={weak ? undefined : t("auth.errors.weakPassword")}
          error={weak ? t("auth.errors.weakPassword") : undefined}
        >
          {({ input }) => (
            <PasswordInput
              id={input}
              autoComplete="new-password"
              autoFocus
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              invalid={weak}
            />
          )}
        </FormField>
        <Button type="submit" loading={mutation.isPending}>
          {t("auth.setPassword")}
        </Button>
      </form>
      <Link to="/login" className="text-center text-label text-ink-500 hover:text-ink-700">
        {t("auth.signIn")}
      </Link>
    </main>
  );
}
