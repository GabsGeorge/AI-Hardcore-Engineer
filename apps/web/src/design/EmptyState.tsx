import type { ReactNode } from "react";

export function EmptyState({
  title,
  description,
  action,
}: {
  title: string;
  description: string;
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-col items-center gap-3 py-12 text-center">
      <div
        aria-hidden="true"
        className="h-10 w-10 rounded-full border border-line bg-surface-200"
      />
      <h3 className="text-heading text-ink-900">{title}</h3>
      <p className="max-w-md text-body text-ink-500">{description}</p>
      {action}
    </div>
  );
}
