import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { useNavigate } from "react-router-dom";
import { Card, EmptyState, Spinner, StatusBadge } from "@/design";
import { api } from "@/lib/api";
import type { HandoffRow } from "./types";

type QueueResponse = { items: HandoffRow[] };

/** Operator queue. Refetches every 30 s (FR-017); priority high rows render first; the SLA
 * breach is shown as a secondary badge next to the priority chip. */
export function QueuePage() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const query = useQuery<QueueResponse>({
    queryKey: ["handoffs", "awaiting_human"],
    queryFn: () => api.get<QueueResponse>("/v1/handoffs?status=awaiting_human&limit=100"),
    refetchInterval: 30_000,
  });

  if (query.isLoading) {
    return (
      <div className="flex items-center gap-2 text-ink-500">
        <Spinner /> <span>{t("app.loading")}</span>
      </div>
    );
  }
  const items = query.data?.items ?? [];
  if (items.length === 0) {
    return <EmptyState title={t("queue.emptyTitle")} description={t("queue.emptyBody")} />;
  }
  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-display text-ink-900">{t("queue.title")}</h1>
      <ul className="flex flex-col gap-2">
        {items.map((item) => (
          <li key={item.ticket_id}>
            <button
              type="button"
              onClick={() => navigate(`/queue/${item.ticket_id}`)}
              className="w-full rounded-md text-left focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-support"
            >
              <Card>
                <div className="flex items-center justify-between gap-3">
                  <div className="flex items-center gap-2">
                    <StatusBadge tone={item.priority === "high" ? "danger" : "neutral"}>
                      {item.priority === "high"
                        ? t("queue.priorityHigh")
                        : t("queue.priorityNormal")}
                    </StatusBadge>
                    {isSlaBreached(item.sla_due_at) ? (
                      <StatusBadge tone="warning">{t("queue.slaBreached")}</StatusBadge>
                    ) : null}
                    <span className="text-label text-ink-400">
                      {t(`queue.reason.${item.reason}`, {
                        defaultValue: item.reason,
                      })}
                    </span>
                  </div>
                  <SlaCountdown slaDueAt={item.sla_due_at} />
                </div>
                <p className="mt-2 line-clamp-2 text-body text-ink-700">{item.summary}</p>
              </Card>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function isSlaBreached(slaDueAt: string): boolean {
  return new Date(slaDueAt).getTime() < Date.now();
}

/** Shows "+N min" when breached, "N min" otherwise. Tabular numbers (DESIGN.md §2.2). */
function SlaCountdown({ slaDueAt }: { slaDueAt: string }) {
  const { t } = useTranslation();
  const delta = Math.round((new Date(slaDueAt).getTime() - Date.now()) / 60_000);
  const label = delta < 0 ? `+${Math.abs(delta)} min` : `${delta} min`;
  return (
    <span
      className="text-label tabular-nums"
      style={{ fontVariantNumeric: "tabular-nums" }}
      aria-label={t("queue.timeRemaining", { minutes: delta })}
    >
      {label}
    </span>
  );
}
