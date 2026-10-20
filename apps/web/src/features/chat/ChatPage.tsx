import { useCallback, useEffect, useRef, useState } from "react";
import { useTranslation } from "react-i18next";
import { useParams } from "react-router-dom";
import { Button, Input, useLiveAnnouncer } from "@/design";
import { streamPost } from "@/lib/sse";
import { HandoffBanner } from "./HandoffBanner";
import { MessageList } from "./MessageList";
import type { ChatMessage, ChatResponseBody, HandoffRef } from "./types";

export function ChatPage() {
  const { t } = useTranslation();
  const announce = useLiveAnnouncer();
  const params = useParams<{ id?: string }>();
  const [input, setInput] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [pending, setPending] = useState(false);
  const [liveSteps, setLiveSteps] = useState<string[]>([]);
  const [handoff, setHandoff] = useState<HandoffRef>({ status: "none", ticket_id: null });
  const [conversationId, setConversationId] = useState<string | undefined>(params.id);
  const [retryAt, setRetryAt] = useState<number | undefined>(undefined);
  const abortRef = useRef<AbortController | null>(null);

  const canSubmit = input.trim().length > 0 && !pending && retryAt === undefined;

  const send = useCallback(
    async (text: string) => {
      const userMessage: ChatMessage = {
        id: `u-${Date.now()}`,
        role: "user",
        content: text,
      };
      setMessages((previous) => [...previous, userMessage]);
      setPending(true);
      setLiveSteps([]);

      const controller = new AbortController();
      abortRef.current = controller;
      try {
        await streamPost(
          "/v1/chat/stream",
          { message: text, conversation_id: conversationId },
          {
            onEvent: (name, data) => {
              if (name === "agent_step") {
                const node = (data as { node?: string }).node ?? "";
                setLiveSteps((steps) => (steps.includes(node) ? steps : [...steps, node]));
              } else if (name === "handoff") {
                const payload = data as HandoffRef;
                setHandoff(payload);
              } else if (name === "done") {
                const final = data as ChatResponseBody;
                setConversationId(final.conversation_id);
                setHandoff(final.handoff);
                setMessages((previous) => [
                  ...previous,
                  {
                    id: `a-${final.trace_id}`,
                    role: "assistant",
                    content: final.response,
                    agentSteps: final.route,
                    sources: final.sources,
                    traceId: final.trace_id,
                  },
                ]);
                announce(final.response);
                setPending(false);
                setLiveSteps([]);
              }
            },
            onError: () => {
              setPending(false);
              setLiveSteps([]);
            },
            onDone: () => {
              setPending(false);
            },
          },
          controller.signal,
        );
      } catch (err) {
        setPending(false);
        setLiveSteps([]);
        if (err instanceof Error && err.message === "sse_http_429") {
          setRetryAt(Date.now() + 60_000);
          window.setTimeout(() => setRetryAt(undefined), 60_000);
        }
      }
    },
    [announce, conversationId],
  );

  function onSubmit(event: React.FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!canSubmit) {
      return;
    }
    const text = input.trim();
    setInput("");
    void send(text);
  }

  useEffect(() => () => abortRef.current?.abort(), []);

  return (
    <div className="flex flex-col gap-6">
      <HandoffBanner handoff={handoff} slaBreached={false} />
      <MessageList messages={messages} pending={pending} liveSteps={liveSteps} />
      <form onSubmit={onSubmit} className="flex items-end gap-2 border-t border-line pt-4">
        <label className="sr-only" htmlFor="chat-input">
          {t("chat.inputLabel")}
        </label>
        <Input
          id="chat-input"
          value={input}
          onChange={(event) => setInput(event.target.value)}
          placeholder={t("chat.inputPlaceholder")}
          disabled={pending || retryAt !== undefined}
          aria-busy={pending || undefined}
        />
        <Button type="submit" loading={pending} disabled={!canSubmit}>
          {t("chat.send")}
        </Button>
      </form>
      {retryAt !== undefined ? (
        <p className="text-label text-state-warning" role="status">
          {t("chat.rateLimited")}
        </p>
      ) : null}
    </div>
  );
}
