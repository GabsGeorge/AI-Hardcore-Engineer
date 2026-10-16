import type { HTMLAttributes, ReactNode } from "react";
import { cn } from "./cn";

export function Card({
  children,
  className,
  ...rest
}: { children: ReactNode } & HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={cn(
        "rounded-md border border-line bg-surface-100 p-4 shadow-1",
        className,
      )}
      {...rest}
    >
      {children}
    </div>
  );
}
