export type Role = "user" | "assistant";

export type Source = {
  title: string;
  url: string;
  kind: "kb" | "web";
  retrieved_at?: string | null;
};

export type ToolCall = { name: string; status: string; latency_ms: number };

export type HandoffRef = {
  status: "none" | "awaiting_human" | "resolved" | "expired";
  ticket_id: string | null;
};

export type ChatResponseBody = {
  response: string;
  conversation_id: string;
  route: string[];
  sources: Source[];
  tools_used: ToolCall[];
  confidence: number;
  handoff: HandoffRef;
  guardrails: { input: string; output: string };
  trace_id: string;
};

export type ChatMessage =
  | { id: string; role: "user"; content: string }
  | {
      id: string;
      role: "assistant";
      content: string;
      agentSteps: string[];
      sources: Source[];
      traceId: string;
    };
