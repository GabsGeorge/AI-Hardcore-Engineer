export type HandoffStatus = "awaiting_human" | "resolved" | "expired";

export type PendingAction = {
  type: "open_dispute";
  params: Record<string, string>;
  decision: "pending" | "approved" | "rejected";
};

export type HandoffRow = {
  ticket_id: string;
  conversation_id: string;
  reason: string;
  status: HandoffStatus;
  priority: "normal" | "high";
  summary: string;
  context: Record<string, unknown>;
  pending_action: PendingAction | null;
  created_at: string;
  sla_due_at: string;
  expires_at: string;
  operator_reply?: string | null;
  resolved_at?: string | null;
};
