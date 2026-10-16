import { cn } from "./cn";

type Tone = "neutral" | "success" | "warning" | "danger" | "brand";

const tones: Record<Tone, string> = {
  neutral: "bg-surface-200 text-ink-700",
  success: "bg-state-success/10 text-state-success",
  warning: "bg-state-warning/10 text-state-warning",
  danger: "bg-state-danger/10 text-state-danger",
  brand: "bg-brand-soft text-brand",
};

export function StatusBadge({ tone = "neutral", children }: { tone?: Tone; children: string }) {
  return (
    <span
      className={cn(
        "inline-flex items-center rounded-sm px-2 py-0.5 text-label font-medium",
        tones[tone],
      )}
    >
      {children}
    </span>
  );
}
