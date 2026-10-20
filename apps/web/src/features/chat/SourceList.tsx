import { useTranslation } from "react-i18next";
import type { Source } from "./types";

/** Clickable sources with a `kb`/`web` tag and the collection date for web sources. The links
 * open in a new tab with `rel="noopener"` so a malicious URL in a retrieved page cannot take
 * over the chat window (FR-012 again). */
export function SourceList({ sources }: { sources: Source[] }) {
  const { t } = useTranslation();
  return (
    <section aria-label={t("chat.sources")} className="max-w-[80%]">
      <h3 className="mb-1 text-label text-ink-500">{t("chat.sources")}</h3>
      <ul className="flex flex-col gap-1">
        {sources.map((source, index) => (
          <li key={`${source.url}-${index}`}>
            <a
              href={source.url}
              target="_blank"
              rel="noopener noreferrer"
              className="text-label text-support hover:underline focus-visible:underline"
            >
              {source.title}
            </a>
            <span className="ml-2 text-label text-ink-400">
              {source.kind.toUpperCase()}
              {source.retrieved_at ? ` · ${source.retrieved_at.slice(0, 10)}` : ""}
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
