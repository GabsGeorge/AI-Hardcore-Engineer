import { useMutation } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { Alert, Button, FormField, Input, Logo, PasswordInput } from "@/design";
import { api, isApiError } from "@/lib/api";

/** Invitee flow: fills name + password, posts to /v1/auth/invites/{token}/accept, bounces to /login. */
export function AcceptInvitePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const [params] = useSearchParams();
  const token = params.get("token") ?? "";
  const [name, setName] = useState("");
  const [password, setPassword] = useState("");
  const [bannerKey, setBannerKey] = useState<string | undefined>();

  const mutation = useMutation({
    mutationFn: () =>
      api.post<{ status: string }>(`/v1/auth/invites/${encodeURIComponent(token)}/accept`, {
        display_name: name,
        new_password: password,
      }),
    onSuccess: () => {
      navigate("/login?invited=1", { replace: true });
    },
    onError: (err) => {
      if (isApiError(err) && err.status === 422) {
        setBannerKey("auth.errors.weakPassword");
      } else if (isApiError(err) && err.status === 410) {
        setBannerKey("admin.invite.fail");
      } else {
        setBannerKey("auth.errors.generic");
      }
    },
  });

  function submit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setBannerKey(undefined);
    if (!token || name.trim().length < 2 || password.length === 0) {
      setBannerKey("auth.errors.generic");
      return;
    }
    mutation.mutate();
  }

  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col justify-center gap-6 p-6">
      <header className="flex flex-col items-center gap-3 text-center">
        <Logo height={40} />
        <h1 className="text-display text-ink-900">{t("admin.invite.title")}</h1>
        <p className="text-body text-ink-500">{t("admin.invite.subtitle")}</p>
      </header>
      {bannerKey ? <Alert tone="danger">{t(bannerKey)}</Alert> : null}
      <form className="flex flex-col gap-4" onSubmit={submit} noValidate>
        <FormField label={t("admin.invite.name")} required>
          {({ input }) => (
            <Input id={input} value={name} onChange={(e) => setName(e.target.value)} />
          )}
        </FormField>
        <FormField label={t("admin.invite.newPassword")} required>
          {({ input }) => (
            <PasswordInput
              id={input}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          )}
        </FormField>
        <Button type="submit" loading={mutation.isPending}>
          {t("admin.invite.submit")}
        </Button>
      </form>
      <nav className="text-label text-ink-500">
        <Link to="/login" className="hover:text-ink-700 focus-visible:underline">
          {t("auth.signIn")}
        </Link>
      </nav>
    </main>
  );
}
