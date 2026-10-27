import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Card, EmptyState, FormField, Input, Spinner, StatusBadge } from "@/design";
import { api } from "@/lib/api";

type AuditEvent = {
  ts: string;
  actor_id: string;
  actor_role: string;
  action: string;
  target: string;
  outcome: "allowed" | "denied" | "error";
  trace_id: string;
};

export function AuditPage() {
  const { t } = useTranslation();
  const [action, setAction] = useState("");
  const [since, setSince] = useState("");

  const query = useQuery<AuditEvent[]>({
    queryKey: ["admin", "audit", action, since],
    queryFn: () => {
      const params = new URLSearchParams();
      if (action.trim()) params.set("action", action.trim());
      if (since) params.set("since", new Date(since).toISOString());
      params.set("limit", "100");
      return api.get<AuditEvent[]>(`/v1/admin/audit?${params.toString()}`);
    },
  });

  return (
    <section className="flex flex-col gap-4">
      <header>
        <h1 className="text-display text-ink-900">{t("admin.audit.title")}</h1>
      </header>

      <Card className="grid gap-3 sm:grid-cols-2">
        <FormField label={t("admin.audit.filterAction")}>
          {({ input }) => (
            <Input
              id={input}
              placeholder="login_ok"
              value={action}
              onChange={(e) => setAction(e.target.value)}
            />
          )}
        </FormField>
        <FormField label={t("admin.audit.filterSince")}>
          {({ input }) => (
            <Input
              id={input}
              type="datetime-local"
              value={since}
              onChange={(e) => setSince(e.target.value)}
            />
          )}
        </FormField>
      </Card>

      {query.isLoading ? (
        <div className="flex items-center gap-2 text-ink-500">
          <Spinner /> <span>{t("app.loading")}</span>
        </div>
      ) : !query.data || query.data.length === 0 ? (
        <EmptyState title={t("admin.audit.emptyTitle")} description={t("admin.audit.emptyBody")} />
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-left text-label">
            <thead className="text-ink-500">
              <tr>
                <th scope="col" className="p-2">
                  {t("admin.audit.columnTs")}
                </th>
                <th scope="col" className="p-2">
                  {t("admin.audit.columnActor")}
                </th>
                <th scope="col" className="p-2">
                  {t("admin.audit.columnAction")}
                </th>
                <th scope="col" className="p-2">
                  {t("admin.audit.columnTarget")}
                </th>
                <th scope="col" className="p-2">
                  {t("admin.audit.columnOutcome")}
                </th>
              </tr>
            </thead>
            <tbody className="text-ink-700">
              {query.data.map((row) => (
                <tr key={`${row.ts}-${row.trace_id}`} className="border-t border-line">
                  <td className="p-2 tabular-nums" style={{ fontVariantNumeric: "tabular-nums" }}>
                    {new Date(row.ts).toLocaleString()}
                  </td>
                  <td className="p-2">
                    {row.actor_id.startsWith("deleted:")
                      ? t("admin.audit.pseudonymised")
                      : row.actor_id}
                  </td>
                  <td className="p-2">{row.action}</td>
                  <td className="break-all p-2">{row.target}</td>
                  <td className="p-2">
                    <StatusBadge
                      tone={
                        row.outcome === "allowed"
                          ? "success"
                          : row.outcome === "denied"
                            ? "warning"
                            : "danger"
                      }
                    >
                      {row.outcome}
                    </StatusBadge>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
