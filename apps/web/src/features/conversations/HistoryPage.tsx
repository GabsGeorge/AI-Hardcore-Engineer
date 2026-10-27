import { useInfiniteQuery } from "@tanstack/react-query";
import { useTranslation } from "react-i18next";
import { Link } from "react-router-dom";
import { Card, EmptyState, Spinner, StatusBadge } from "@/design";
import { api } from "@/lib/api";

type HandoffStatus = "none" | "awaiting_human" | "resolved" | "expired";
type Summary = {
  id: string;
  started_at: string;
  last_activity_at: string;
  handoff_status: HandoffStatus;
  last_message_preview: string;
};
type Page = { items: Summary[]; next_cursor: string | null };

const PAGE_SIZE = 20;

export function HistoryPage() {
  const { t, i18n } = useTranslation();
  const query = useInfiniteQuery<Page>({
    queryKey: ["me", "conversations"],
    initialPageParam: null as string | null,
    getNextPageParam: (lastPage) => lastPage.next_cursor,
    queryFn: ({ pageParam }) => {
      const url = new URL("/v1/me/conversations", window.location.origin);
      url.searchParams.set("limit", String(PAGE_SIZE));
      if (pageParam !== null) {
        url.searchParams.set("cursor", pageParam as string);
      }
      return api.get<Page>(`${url.pathname}${url.search}`);
    },
  });

  if (query.isLoading) {
    return (
      <div className="flex items-center gap-2 text-ink-500">
        <Spinner /> <span>{t("app.loading")}</span>
      </div>
    );
  }

  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  if (items.length === 0) {
    return (
      <EmptyState
        title={t("history.emptyTitle")}
        description={t("history.emptyBody")}
        action={
          <Link to="/chat" className="text-label text-brand hover:underline">
            {t("history.start")}
          </Link>
        }
      />
    );
  }

  return (
    <div className="flex flex-col gap-4">
      <h1 className="text-display text-ink-900">{t("history.title")}</h1>
      <ul className="flex flex-col gap-2">
        {items.map((item) => (
          <li key={item.id}>
            <Link
              to={`/chat/${item.id}`}
              className="block rounded-md focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-support"
            >
              <Card className="hover:bg-surface-200">
                <div className="flex items-center justify-between gap-3">
                  <span className="text-label text-ink-400">
                    {formatDate(item.last_activity_at, i18n.language)}
                  </span>
                  <HandoffChip status={item.handoff_status} />
                </div>
                <p className="mt-2 line-clamp-1 text-body text-ink-700">
                  {item.last_message_preview || t("history.noPreview")}
                </p>
              </Card>
            </Link>
          </li>
        ))}
      </ul>
      {query.hasNextPage ? (
        <button
          type="button"
          onClick={() => void query.fetchNextPage()}
          disabled={query.isFetchingNextPage}
          className="self-center rounded-md border border-line bg-surface-100 px-4 py-2 text-label text-ink-700 hover:bg-surface-200 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-support disabled:opacity-60"
        >
          {query.isFetchingNextPage ? t("history.loadingMore") : t("history.loadMore")}
        </button>
      ) : null}
    </div>
  );
}

function HandoffChip({ status }: { status: HandoffStatus }) {
  const { t } = useTranslation();
  if (status === "none") {
    return null;
  }
  const tone =
    status === "awaiting_human" ? "warning" : status === "resolved" ? "success" : "danger";
  return <StatusBadge tone={tone}>{t(`history.status.${status}`)}</StatusBadge>;
}

function formatDate(iso: string, lang: string): string {
  try {
    return new Intl.DateTimeFormat(lang === "en" ? "en-US" : "pt-BR", {
      year: "numeric",
      month: "short",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
    }).format(new Date(iso));
  } catch {
    return iso;
  }
}
