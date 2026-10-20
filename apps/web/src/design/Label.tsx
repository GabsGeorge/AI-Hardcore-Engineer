import type { LabelHTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

export function Label({
  children,
  required,
  className,
  ...rest
}: {
  children: ReactNode;
  required?: boolean;
  className?: string;
} & LabelHTMLAttributes<HTMLLabelElement>) {
  return (
    <label className={cn("text-label text-ink-500", className)} {...rest}>
      {children}
      {required ? (
        <span aria-hidden="true" className="text-state-danger">
          {" "}
          *
        </span>
      ) : null}
    </label>
  );
}
