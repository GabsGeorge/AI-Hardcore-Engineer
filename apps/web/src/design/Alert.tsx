import type { ReactNode } from "react";
import { cn } from "./cn";

type Tone = "info" | "success" | "warning" | "danger";

const tones: Record<Tone, { bg: string; text: string; role: "status" | "alert" }> = {
  info: { bg: "bg-surface-200", text: "text-ink-700", role: "status" },
  success: { bg: "bg-state-success/10", text: "text-state-success", role: "status" },
  warning: { bg: "bg-state-warning/10", text: "text-state-warning", role: "status" },
  danger: { bg: "bg-brand-soft", text: "text-state-danger", role: "alert" },
};

export function Alert({
  tone = "info",
  title,
  children,
  className,
}: {
  tone?: Tone;
  title?: string;
  children: ReactNode;
  className?: string;
}) {
  const t = tones[tone];
  return (
    <div className={cn("rounded-md p-3 text-body", t.bg, t.text, className)} role={t.role}>
      {title ? <p className="font-semibold">{title}</p> : null}
      <div>{children}</div>
    </div>
  );
}
