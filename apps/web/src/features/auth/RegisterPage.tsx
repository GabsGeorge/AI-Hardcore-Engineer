import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { z } from "zod";
import { Alert, Button, FormField, Input, Logo, PasswordInput } from "@/design";
import { api, isApiError } from "@/lib/api";

const Schema = z.object({
  display_name: z.string().min(2).max(80),
  email: z.string().email(),
  password: z.string().min(12).max(256),
});

type RegisterBody = z.infer<typeof Schema>;

export function RegisterPage() {
  const { t } = useTranslation();
  const [body, setBody] = useState<RegisterBody>({
    display_name: "",
    email: "",
    password: "",
  });
  const [weakPassword, setWeakPassword] = useState(false);
  const [generic, setGeneric] = useState(false);

  const mutation = useMutation({
    mutationFn: (payload: RegisterBody) =>
      api.post<{ status: "pending" }>("/v1/auth/register", payload),
    onError: (err) => {
      if (isApiError(err) && err.code === "weak_password") {
        setWeakPassword(true);
        return;
      }
      setGeneric(true);
    },
  });

  function set<K extends keyof RegisterBody>(key: K, value: RegisterBody[K]) {
    setBody((current) => ({ ...current, [key]: value }));
  }

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = Schema.safeParse(body);
    setGeneric(false);
    if (!parsed.success) {
      setWeakPassword(parsed.error.issues.some((i) => i.path[0] === "password"));
      return;
    }
    setWeakPassword(false);
    mutation.mutate(parsed.data);
  }

  if (mutation.isSuccess) {
    return (
      <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 p-6">
        <header className="flex flex-col items-center gap-3 text-center">
          <Logo height={40} />
          <h1 className="text-display text-ink-900">{t("auth.confirmSentTitle")}</h1>
          <p className="text-body text-ink-500">{t("auth.confirmSentBody")}</p>
        </header>
        <Link to="/login" className="text-center text-label text-brand hover:underline">
          {t("auth.signIn")}
        </Link>
      </main>
    );
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 p-6">
      <header className="flex flex-col items-center gap-3 text-center">
        <Logo height={40} />
        <h1 className="text-display text-ink-900">{t("auth.createAccountTitle")}</h1>
      </header>
      {generic ? <Alert tone="danger">{t("auth.errors.generic")}</Alert> : null}
      <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
        <FormField label={t("auth.name")} required>
          {({ input }) => (
            <Input
              id={input}
              autoComplete="name"
              value={body.display_name}
              onChange={(e) => set("display_name", e.target.value)}
            />
          )}
        </FormField>
        <FormField label={t("auth.email")} required>
          {({ input }) => (
            <Input
              id={input}
              type="email"
              autoComplete="email"
              value={body.email}
              onChange={(e) => set("email", e.target.value)}
            />
          )}
        </FormField>
        <FormField
          label={t("auth.password")}
          required
          help={weakPassword ? undefined : t("auth.errors.weakPassword")}
          error={weakPassword ? t("auth.errors.weakPassword") : undefined}
        >
          {({ input }) => (
            <PasswordInput
              id={input}
              autoComplete="new-password"
              value={body.password}
              onChange={(e) => set("password", e.target.value)}
              invalid={weakPassword}
            />
          )}
        </FormField>
        <Button type="submit" loading={mutation.isPending}>
          {t("auth.createAccount")}
        </Button>
      </form>
      <Link to="/login" className="text-center text-label text-ink-500 hover:text-ink-700">
        {t("auth.signIn")}
      </Link>
    </main>
  );
}
