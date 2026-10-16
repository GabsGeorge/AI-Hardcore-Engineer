import type { ButtonHTMLAttributes, ReactNode } from "react";
import { Spinner } from "./Spinner";
import { cn } from "./cn";

type Intent = "primary" | "secondary" | "ghost";
type Size = "sm" | "md" | "lg";

const base =
  "inline-flex items-center justify-center gap-2 rounded-md font-medium transition-colors " +
  "duration-fast ease-standard outline-none focus-visible:ring-2 focus-visible:ring-support " +
  "focus-visible:ring-offset-2 focus-visible:ring-offset-page " +
  "disabled:cursor-not-allowed disabled:opacity-60";

const bySize: Record<Size, string> = {
  sm: "h-8 px-3 text-label",
  md: "h-10 px-4 text-body",
  lg: "h-12 px-5 text-body",
};

const byIntent: Record<Intent, string> = {
  primary: "bg-brand text-surface-100 hover:bg-brand-hover active:bg-brand-pressed",
  secondary:
    "border border-line bg-surface-100 text-ink-700 hover:bg-surface-200 active:bg-line",
  ghost: "bg-transparent text-ink-700 hover:bg-surface-200 active:bg-line",
};

export function Button({
  intent = "primary",
  size = "md",
  loading = false,
  children,
  className,
  ...rest
}: {
  intent?: Intent;
  size?: Size;
  loading?: boolean;
  children: ReactNode;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      className={cn(base, bySize[size], byIntent[intent], className)}
      disabled={rest.disabled || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Spinner size={size === "sm" ? 14 : 16} /> : null}
      {children}
    </button>
  );
}
