import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { z } from "zod";
import { Alert, Button, FormField, Input, Logo, PasswordInput } from "@/design";
import { api, isApiError } from "@/lib/api";

const Schema = z.object({
  email: z.string().email(),
  password: z.string().min(1),
});

type LoginBody = z.infer<typeof Schema>;
type Account = { id: string; role: "merchant" | "operator" | "admin"; display_name: string };

export function LoginPage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const client = useQueryClient();
  const [params] = useSearchParams();
  const next = params.get("next") ?? "/chat";
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [emailError, setEmailError] = useState<string | undefined>();
  const [bannerKey, setBannerKey] = useState<string | undefined>();
  const [retrySeconds, setRetrySeconds] = useState<number | undefined>();

  const mutation = useMutation({
    mutationFn: async (body: LoginBody) =>
      api.post<{ account: Account }>("/v1/auth/login", body),
    onSuccess: ({ account }) => {
      client.setQueryData(["session"], account);
      navigate(next, { replace: true });
    },
    onError: (err) => {
      if (!isApiError(err)) {
        setBannerKey("auth.errors.generic");
        return;
      }
      if (err.status === 423) {
        setBannerKey("auth.errors.locked");
        setRetrySeconds(err.retryAfterSeconds);
      } else if (err.status === 429) {
        setBannerKey("auth.errors.rateLimited");
        setRetrySeconds(err.retryAfterSeconds);
      } else {
        setBannerKey("auth.errors.credentials");
      }
    },
  });

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const parsed = Schema.safeParse({ email, password });
    if (!parsed.success) {
      setEmailError(parsed.error.issues.find((i) => i.path[0] === "email") ? "invalid" : undefined);
      return;
    }
    setEmailError(undefined);
    setBannerKey(undefined);
    mutation.mutate(parsed.data);
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 p-6">
      <header className="flex flex-col items-center gap-3 text-center">
        <Logo height={40} />
        <h1 className="text-display text-ink-900">{t("auth.signInTitle")}</h1>
        <p className="text-body text-ink-500">{t("auth.signInSubtitle")}</p>
      </header>
      {bannerKey ? (
        <Alert tone="danger">
          {t(bannerKey, { seconds: retrySeconds ?? "" })}
        </Alert>
      ) : null}
      <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
        <FormField
          label={t("auth.email")}
          required
          error={emailError ? t("auth.errors.credentials") : undefined}
        >
          {({ input }) => (
            <Input
              id={input}
              type="email"
              autoComplete="email"
              autoFocus
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              invalid={Boolean(emailError)}
            />
          )}
        </FormField>
        <FormField label={t("auth.password")} required>
          {({ input }) => (
            <PasswordInput
              id={input}
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
        </FormField>
        <Button type="submit" loading={mutation.isPending}>
          {t("auth.signIn")}
        </Button>
      </form>
      <nav className="flex flex-wrap items-center justify-between gap-3 text-label text-ink-500">
        <Link to="/forgot" className="hover:text-ink-700 focus-visible:underline">
          {t("auth.forgot")}
        </Link>
        <Link to="/register" className="hover:text-ink-700 focus-visible:underline">
          {t("auth.register")}
        </Link>
      </nav>
    </main>
  );
}
