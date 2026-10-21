import { useEffect, useRef, type ReactNode } from "react";
import { cn } from "./cn";

/**
 * Minimal modal dialog. Uses the native <dialog> element so focus trap, Esc close, inert
 * background and the backdrop are handled by the browser. The scrim colour is overridden to
 * match the token.
 */
export function Dialog({
  open,
  onClose,
  title,
  children,
  footer,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  footer?: ReactNode;
}) {
  const ref = useRef<HTMLDialogElement | null>(null);
  useEffect(() => {
    const node = ref.current;
    if (node === null) {
      return;
    }
    if (open && !node.open) {
      node.showModal();
    }
    if (!open && node.open) {
      node.close();
    }
  }, [open]);
  return (
    <dialog
      ref={ref}
      className={cn(
        "w-full max-w-md rounded-md bg-surface-100 p-6 shadow-2 backdrop:bg-ink-900/50",
        "sm:bottom-auto sm:top-1/2 sm:-translate-y-1/2",
      )}
      aria-labelledby={`${title.replace(/\s+/g, "-").toLowerCase()}-title`}
      onClose={onClose}
    >
      <div className="flex items-start justify-between gap-4">
        <h2
          id={`${title.replace(/\s+/g, "-").toLowerCase()}-title`}
          className="text-heading text-ink-900"
        >
          {title}
        </h2>
      </div>
      <div className="mt-4 text-body text-ink-700">{children}</div>
      {footer ? <div className="mt-6 flex justify-end gap-2">{footer}</div> : null}
    </dialog>
  );
}
