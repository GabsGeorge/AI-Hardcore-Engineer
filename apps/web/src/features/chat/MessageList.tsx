import { useTranslation } from "react-i18next";
import { Spinner, StatusBadge } from "@/design";
import { SourceList } from "./SourceList";
import type { ChatMessage } from "./types";

/** Rendered conversation. Text content is bound via React children, never innerHTML, so a
 * model answer that contains HTML or JS stays inert (FR-012 covered on the backend by
 * tests/security/test_chat_render.py). */
export function MessageList({
  messages,
  pending,
  liveSteps,
}: {
  messages: ChatMessage[];
  pending: boolean;
  liveSteps: string[];
}) {
  const { t } = useTranslation();
  return (
    <ol
      className="flex flex-col gap-4"
      aria-live="polite"
      aria-relevant="additions"
      role="log"
    >
      {messages.map((message) =>
        message.role === "user" ? (
          <li key={message.id} className="flex justify-end">
            <div className="max-w-[80%] rounded-lg bg-surface-200 p-3 text-body text-ink-700">
              {message.content}
            </div>
          </li>
        ) : (
          <li key={message.id} className="flex flex-col gap-2">
            {message.agentSteps.length > 0 ? (
              <div className="flex flex-wrap gap-1">
                {message.agentSteps.map((step) => (
                  <StatusBadge key={step}>{step}</StatusBadge>
                ))}
              </div>
            ) : null}
            <div className="max-w-[80%] rounded-lg border border-line bg-surface-100 p-3 text-body text-ink-700 shadow-1">
              {message.content}
            </div>
            {message.sources.length > 0 ? <SourceList sources={message.sources} /> : null}
          </li>
        ),
      )}
      {pending ? (
        <li className="flex flex-col gap-2">
          {liveSteps.length > 0 ? (
            <div className="flex flex-wrap gap-1">
              {liveSteps.map((step) => (
                <StatusBadge key={step}>{step}</StatusBadge>
              ))}
            </div>
          ) : null}
          <div className="flex max-w-[80%] items-center gap-2 rounded-lg border border-line bg-surface-100 p-3 text-body text-ink-500 shadow-1">
            <Spinner />
            <span>{t("chat.thinking")}</span>
          </div>
        </li>
      ) : null}
    </ol>
  );
}
