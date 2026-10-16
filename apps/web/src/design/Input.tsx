import type { InputHTMLAttributes } from "react";
import { cn } from "./cn";

export function Input({
  invalid,
  className,
  ...rest
}: { invalid?: boolean } & InputHTMLAttributes<HTMLInputElement>) {
  return (
    <input
      className={cn(
        "h-10 w-full rounded-md border bg-surface-100 px-3 text-body text-ink-700",
        "placeholder:text-ink-400 outline-none",
        "focus-visible:ring-2 focus-visible:ring-support focus-visible:ring-offset-2",
        "focus-visible:ring-offset-page",
        invalid ? "border-state-danger" : "border-line",
        className,
      )}
      aria-invalid={invalid || undefined}
      {...rest}
    />
  );
}
