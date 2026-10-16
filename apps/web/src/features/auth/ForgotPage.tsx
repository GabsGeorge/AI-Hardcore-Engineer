import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { z } from "zod";
import { Alert, Button, FormField, Input, Logo } from "@/design";
import { api } from "@/lib/api";

const Schema = z.object({ email: z.string().email() });

export function ForgotPage() {
  const { t } = useTranslation();
  const [email, setEmail] = useState("");
  const mutation = useMutation({
    mutationFn: (body: { email: string }) =>
      api.post<{ status: "pending" }>("/v1/auth/password/reset-request", body),
  });

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = Schema.safeParse({ email });
    if (parsed.success) {
      mutation.mutate(parsed.data);
    }
  }

  if (mutation.isSuccess) {
    return (
      <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 p-6 text-center">
        <Logo height={40} />
        <h1 className="text-display text-ink-900">{t("auth.confirmSentTitle")}</h1>
        <p className="text-body text-ink-500">{t("auth.confirmSentBody")}</p>
        <Link to="/login" className="text-label text-brand hover:underline">
          {t("auth.signIn")}
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 p-6">
      <header className="flex flex-col items-center gap-3 text-center">
        <Logo height={40} />
        <h1 className="text-display text-ink-900">{t("auth.forgot")}</h1>
      </header>
      {mutation.isError ? <Alert tone="danger">{t("auth.errors.generic")}</Alert> : null}
      <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
        <FormField label={t("auth.email")} required>
          {({ input }) => (
            <Input
              id={input}
              type="email"
              autoComplete="email"
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          )}
        </FormField>
        <Button type="submit" loading={mutation.isPending}>
          {t("auth.sendReset")}
        </Button>
      </form>
      <Link to="/login" className="text-center text-label text-ink-500 hover:text-ink-700">
        {t("auth.signIn")}
      </Link>
    </main>
  );
}
