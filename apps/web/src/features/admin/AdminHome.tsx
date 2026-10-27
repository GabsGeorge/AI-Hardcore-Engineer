import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Button, Card } from "@/design";

/** Admin landing: four tiles pointing at the sub-pages. Shown only inside RoleGuard(["admin"]). */
export function AdminHome() {
  const { t } = useTranslation();
  const tiles = [
    {
      to: "/admin/accounts",
      title: "admin.home.accountsTitle",
      body: "admin.home.accountsBody",
      cta: "admin.home.accountsAction",
    },
    {
      to: "/admin/merchants",
      title: "admin.home.linkTitle",
      body: "admin.home.linkBody",
      cta: "admin.home.linkAction",
    },
    {
      to: "/admin/queue",
      title: "admin.home.queueTitle",
      body: "admin.home.queueBody",
      cta: "admin.home.queueAction",
    },
    {
      to: "/admin/audit",
      title: "admin.home.auditTitle",
      body: "admin.home.auditBody",
      cta: "admin.home.auditAction",
    },
  ] as const;
  return (
    <section className="flex flex-col gap-4">
      <header>
        <h1 className="text-display text-ink-900">{t("admin.home.title")}</h1>
        <p className="text-body text-ink-500">{t("admin.home.subtitle")}</p>
      </header>
      <div className="grid gap-4 sm:grid-cols-2">
        {tiles.map((tile) => (
          <Card key={tile.to} className="flex flex-col gap-3">
            <h2 className="text-heading text-ink-900">{t(tile.title)}</h2>
            <p className="text-body text-ink-500">{t(tile.body)}</p>
            <div>
              <Link to={tile.to}>
                <Button intent="secondary">{t(tile.cta)}</Button>
              </Link>
            </div>
          </Card>
        ))}
      </div>
    </section>
  );
}
