import { useQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Button, Card, Spinner } from "@/design";
import { api } from "@/lib/api";

type Overview = {
  awaiting_human: number;
  sla_breached_today: number;
  expired_today: number;
};

export function QueueOverviewPage() {
  const { t } = useTranslation();
  const query = useQuery<Overview>({
    queryKey: ["admin", "queue-overview"],
    queryFn: () => api.get<Overview>("/v1/admin/queue"),
    refetchInterval: 30_000,
  });

  if (query.isLoading) {
    return (
      <div className="flex items-center gap-2 text-ink-500">
        <Spinner /> <span>{t("app.loading")}</span>
      </div>
    );
  }
  const d = query.data ?? { awaiting_human: 0, sla_breached_today: 0, expired_today: 0 };
  return (
    <section className="flex flex-col gap-4">
      <header>
        <h1 className="text-display text-ink-900">{t("admin.queueOverview.title")}</h1>
      </header>
      <div className="grid gap-4 sm:grid-cols-3">
        <Tile label={t("admin.queueOverview.awaiting")} value={d.awaiting_human} />
        <Tile label={t("admin.queueOverview.slaBreached")} value={d.sla_breached_today} />
        <Tile label={t("admin.queueOverview.expired")} value={d.expired_today} />
      </div>
      <div>
        <Link to="/queue">
          <Button intent="secondary">{t("admin.queueOverview.goToQueue")}</Button>
        </Link>
      </div>
    </section>
  );
}

function Tile({ label, value }: { label: string; value: number }) {
  return (
    <Card className="flex flex-col gap-1">
      <span className="text-label text-ink-500">{label}</span>
      <strong
        className="text-display tabular-nums text-ink-900"
        style={{ fontVariantNumeric: "tabular-nums" }}
      >
        {value}
      </strong>
    </Card>
  );
}
