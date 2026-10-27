import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Alert, Button, Card, FormField, Input } from "@/design";
import { api, isApiError } from "@/lib/api";

type Account = {
  id: string;
  email: string;
  display_name: string;
  role: "merchant" | "operator" | "admin";
  status: string;
  linked_merchant_id: string | null;
};

export function MerchantLinkPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [merchantId, setMerchantId] = useState("");
  const [accountId, setAccountId] = useState("");
  const [toast, setToast] = useState<{ kind: "ok" | "err"; messageKey: string } | null>(null);

  const accounts = useQuery<Account[]>({
    queryKey: ["admin", "accounts", "merchant"],
    queryFn: () => api.get<Account[]>("/v1/admin/accounts?role=merchant&limit=100"),
  });

  const link = useMutation({
    mutationFn: () =>
      api.post<Response>(`/v1/admin/merchants/${encodeURIComponent(merchantId)}/link`, {
        account_id: accountId,
      }),
    onSuccess: () => {
      setToast({ kind: "ok", messageKey: "admin.link.linked" });
      qc.invalidateQueries({ queryKey: ["admin", "accounts"] });
    },
    onError: (err) => {
      if (isApiError(err) && err.status === 409) {
        setToast({ kind: "err", messageKey: "admin.link.conflict" });
      } else {
        setToast({ kind: "err", messageKey: "admin.link.sendError" });
      }
    },
  });

  const unlink = useMutation({
    mutationFn: () =>
      api.delete<Response>(`/v1/admin/merchants/${encodeURIComponent(merchantId)}/link`),
    onSuccess: () => {
      setToast({ kind: "ok", messageKey: "admin.link.unlinked" });
      qc.invalidateQueries({ queryKey: ["admin", "accounts"] });
    },
    onError: () => setToast({ kind: "err", messageKey: "admin.link.sendError" }),
  });

  const canLink = merchantId.trim().length > 0 && accountId.length > 0;

  return (
    <section className="flex flex-col gap-4">
      <header>
        <h1 className="text-display text-ink-900">{t("admin.link.title")}</h1>
        <p className="text-body text-ink-500">{t("admin.link.subtitle")}</p>
      </header>

      {toast ? (
        <Alert tone={toast.kind === "ok" ? "info" : "danger"}>{t(toast.messageKey)}</Alert>
      ) : null}

      <Card className="flex flex-col gap-3">
        <FormField label={t("admin.link.merchantIdLabel")} required>
          {({ input }) => (
            <Input
              id={input}
              placeholder="cliente1988"
              value={merchantId}
              onChange={(e) => setMerchantId(e.target.value)}
            />
          )}
        </FormField>

        <label className="flex flex-col gap-1 text-label text-ink-500">
          <span>{t("admin.link.accountLabel")}</span>
          <select
            className="h-10 rounded-md border border-line bg-surface-100 px-3 text-body text-ink-700"
            value={accountId}
            onChange={(e) => setAccountId(e.target.value)}
          >
            <option value="">{t("admin.link.selectAccount")}</option>
            {(accounts.data ?? []).map((acc) => (
              <option key={acc.id} value={acc.id}>
                {acc.display_name} — {acc.email}
                {acc.linked_merchant_id ? ` (${acc.linked_merchant_id})` : ""}
              </option>
            ))}
          </select>
        </label>

        <div className="flex flex-wrap gap-2">
          <Button loading={link.isPending} disabled={!canLink} onClick={() => link.mutate()}>
            {t("admin.link.linkAction")}
          </Button>
          <Button
            intent="secondary"
            disabled={merchantId.trim().length === 0}
            loading={unlink.isPending}
            onClick={() => unlink.mutate()}
          >
            {t("admin.link.unlinkAction")}
          </Button>
        </div>
      </Card>
    </section>
  );
}
