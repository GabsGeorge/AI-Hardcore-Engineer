import { useTranslation } from "react-i18next";

export function NotFound() {
  const { t } = useTranslation();
  return (
    <main className="mx-auto flex min-h-screen max-w-md flex-col items-center justify-center gap-4 p-8 text-center">
      <h1 className="text-display text-ink-900">{t("notFound.title")}</h1>
      <p className="text-body text-ink-500">{t("notFound.body")}</p>
    </main>
  );
}
