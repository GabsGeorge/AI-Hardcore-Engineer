import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import {
  Alert,
  Button,
  Card,
  Dialog,
  EmptyState,
  FormField,
  Input,
  Spinner,
  StatusBadge,
} from "@/design";
import { api, isApiError } from "@/lib/api";

type Account = {
  id: string;
  email: string;
  display_name: string;
  role: "merchant" | "operator" | "admin";
  status: "pending" | "active" | "locked" | "deactivated";
  linked_merchant_id: string | null;
};

type RoleFilter = "" | Account["role"];
type StatusFilter = "" | Account["status"];

const ROLES: RoleFilter[] = ["", "merchant", "operator", "admin"];
const STATUSES: StatusFilter[] = ["", "pending", "active", "locked", "deactivated"];

export function AccountsPage() {
  const { t } = useTranslation();
  const qc = useQueryClient();
  const [role, setRole] = useState<RoleFilter>("");
  const [status, setStatus] = useState<StatusFilter>("");
  const [inviteOpen, setInviteOpen] = useState(false);
  const [toast, setToast] = useState<{ kind: "ok" | "err"; messageKey: string } | null>(null);

  const list = useQuery<Account[]>({
    queryKey: ["admin", "accounts", role, status],
    queryFn: () => {
      const params = new URLSearchParams();
      if (role) params.set("role", role);
      if (status) params.set("status", status);
      params.set("limit", "100");
      return api.get<Account[]>(`/v1/admin/accounts?${params.toString()}`);
    },
  });

  const deactivate = useMutation({
    mutationFn: (id: string) => api.post<Response>(`/v1/admin/accounts/${id}/deactivate`),
    onSuccess: () => {
      setToast({ kind: "ok", messageKey: "admin.accounts.deactivated" });
      qc.invalidateQueries({ queryKey: ["admin", "accounts"] });
    },
    onError: () => setToast({ kind: "err", messageKey: "admin.accounts.sendError" }),
  });

  const activate = useMutation({
    mutationFn: (id: string) => api.post<Response>(`/v1/admin/accounts/${id}/activate`),
    onSuccess: () => {
      setToast({ kind: "ok", messageKey: "admin.accounts.activated" });
      qc.invalidateQueries({ queryKey: ["admin", "accounts"] });
    },
    onError: () => setToast({ kind: "err", messageKey: "admin.accounts.sendError" }),
  });

  return (
    <section className="flex flex-col gap-4">
      <header className="flex flex-wrap items-end justify-between gap-3">
        <h1 className="text-display text-ink-900">{t("admin.accounts.title")}</h1>
        <Button onClick={() => setInviteOpen(true)}>{t("admin.accounts.invite")}</Button>
      </header>

      <Card className="flex flex-wrap gap-4">
        <label className="flex flex-col gap-1 text-label text-ink-500">
          <span>{t("admin.accounts.filterRole")}</span>
          <select
            className="h-10 rounded-md border border-line bg-surface-100 px-3 text-body text-ink-700"
            value={role}
            onChange={(e) => setRole(e.target.value as RoleFilter)}
          >
            {ROLES.map((r) => (
              <option key={r || "any"} value={r}>
                {r || t("admin.accounts.any")}
              </option>
            ))}
          </select>
        </label>
        <label className="flex flex-col gap-1 text-label text-ink-500">
          <span>{t("admin.accounts.filterStatus")}</span>
          <select
            className="h-10 rounded-md border border-line bg-surface-100 px-3 text-body text-ink-700"
            value={status}
            onChange={(e) => setStatus(e.target.value as StatusFilter)}
          >
            {STATUSES.map((s) => (
              <option key={s || "any"} value={s}>
                {s || t("admin.accounts.any")}
              </option>
            ))}
          </select>
        </label>
      </Card>

      {toast ? (
        <Alert tone={toast.kind === "ok" ? "info" : "danger"}>{t(toast.messageKey)}</Alert>
      ) : null}

      {list.isLoading ? (
        <div className="flex items-center gap-2 text-ink-500">
          <Spinner /> <span>{t("app.loading")}</span>
        </div>
      ) : !list.data || list.data.length === 0 ? (
        <EmptyState
          title={t("admin.accounts.emptyTitle")}
          description={t("admin.accounts.emptyBody")}
        />
      ) : (
        <ul className="flex flex-col gap-2">
          {list.data.map((acc) => (
            <li key={acc.id}>
              <Card>
                <div className="flex flex-wrap items-center justify-between gap-3">
                  <div className="flex flex-col gap-1">
                    <strong className="text-body text-ink-900">{acc.display_name}</strong>
                    <span className="text-label text-ink-500">{acc.email}</span>
                    <span className="text-label text-ink-400">
                      {acc.linked_merchant_id
                        ? t("admin.accounts.linked", { merchant: acc.linked_merchant_id })
                        : t("admin.accounts.notLinked")}
                    </span>
                  </div>
                  <div className="flex flex-wrap items-center gap-2">
                    <StatusBadge tone="neutral">{acc.role}</StatusBadge>
                    <StatusBadge
                      tone={
                        acc.status === "active"
                          ? "success"
                          : acc.status === "deactivated"
                            ? "danger"
                            : "warning"
                      }
                    >
                      {acc.status}
                    </StatusBadge>
                    {acc.status === "deactivated" ? (
                      <Button
                        intent="secondary"
                        size="sm"
                        onClick={() => activate.mutate(acc.id)}
                        loading={activate.isPending && activate.variables === acc.id}
                      >
                        {t("admin.accounts.activate")}
                      </Button>
                    ) : (
                      <Button
                        intent="secondary"
                        size="sm"
                        onClick={() => {
                          if (window.confirm(t("admin.accounts.deactivateConfirmBody"))) {
                            deactivate.mutate(acc.id);
                          }
                        }}
                        loading={deactivate.isPending && deactivate.variables === acc.id}
                      >
                        {t("admin.accounts.deactivate")}
                      </Button>
                    )}
                  </div>
                </div>
              </Card>
            </li>
          ))}
        </ul>
      )}

      <InviteDialog
        open={inviteOpen}
        onClose={() => setInviteOpen(false)}
        onSuccess={() => {
          setToast({ kind: "ok", messageKey: "admin.accounts.inviteSent" });
          qc.invalidateQueries({ queryKey: ["admin", "accounts"] });
        }}
        onError={() => setToast({ kind: "err", messageKey: "admin.accounts.sendError" })}
      />
    </section>
  );
}

function InviteDialog({
  open,
  onClose,
  onSuccess,
  onError,
}: {
  open: boolean;
  onClose: () => void;
  onSuccess: () => void;
  onError: () => void;
}) {
  const { t } = useTranslation();
  const [name, setName] = useState("");
  const [email, setEmail] = useState("");
  const [role, setRole] = useState<"operator" | "admin">("operator");

  const mutation = useMutation({
    mutationFn: () =>
      api.post<{ status: string }>("/v1/admin/accounts", {
        display_name: name,
        email,
        role,
      }),
    onSuccess: () => {
      onSuccess();
      setName("");
      setEmail("");
      setRole("operator");
      onClose();
    },
    onError: (err) => {
      if (isApiError(err)) onError();
      else onError();
    },
  });

  return (
    <Dialog
      open={open}
      onClose={onClose}
      title={t("admin.accounts.inviteDialogTitle")}
      footer={
        <>
          <Button intent="ghost" onClick={onClose}>
            {t("admin.accounts.cancel")}
          </Button>
          <Button loading={mutation.isPending} onClick={() => mutation.mutate()}>
            {t("admin.accounts.inviteSend")}
          </Button>
        </>
      }
    >
      <div className="flex flex-col gap-3">
        <FormField label={t("admin.accounts.inviteName")} required>
          {({ input }) => (
            <Input id={input} value={name} onChange={(e) => setName(e.target.value)} />
          )}
        </FormField>
        <FormField label={t("admin.accounts.inviteEmail")} required>
          {({ input }) => (
            <Input
              id={input}
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
            />
          )}
        </FormField>
        <label className="flex flex-col gap-1 text-label text-ink-500">
          <span>{t("admin.accounts.inviteRole")}</span>
          <select
            className="h-10 rounded-md border border-line bg-surface-100 px-3 text-body text-ink-700"
            value={role}
            onChange={(e) => setRole(e.target.value as "operator" | "admin")}
          >
            <option value="operator">operator</option>
            <option value="admin">admin</option>
          </select>
        </label>
      </div>
    </Dialog>
  );
}
