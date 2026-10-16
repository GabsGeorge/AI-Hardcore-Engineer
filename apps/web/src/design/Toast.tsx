import { createContext, useCallback, useContext, useEffect, useRef, useState, type ReactNode } from "react";
import { cn } from "./cn";

type Tone = "success" | "warning" | "danger";

type ToastItem = { id: number; tone: Tone; text: string };

const ToastContext = createContext<((text: string, tone?: Tone) => void) | null>(null);

export function ToastProvider({ children }: { children: ReactNode }) {
  const [items, setItems] = useState<ToastItem[]>([]);
  const nextId = useRef(1);
  const push = useCallback((text: string, tone: Tone = "success") => {
    const id = nextId.current++;
    setItems((xs) => [...xs, { id, tone, text }]);
    window.setTimeout(() => {
      setItems((xs) => xs.filter((x) => x.id !== id));
    }, 5000);
  }, []);
  return (
    <ToastContext.Provider value={push}>
      {children}
      <div className="pointer-events-none fixed bottom-4 left-4 flex flex-col gap-2">
        {items.map((item) => (
          <Toast key={item.id} tone={item.tone}>
            {item.text}
          </Toast>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast() {
  const context = useContext(ToastContext);
  if (context === null) {
    throw new Error("useToast must be called inside <ToastProvider>");
  }
  return context;
}

const tones: Record<Tone, { bg: string; role: "status" | "alert" }> = {
  success: { bg: "bg-state-success text-surface-100", role: "status" },
  warning: { bg: "bg-state-warning text-surface-100", role: "status" },
  danger:  { bg: "bg-state-danger text-surface-100", role: "alert" },
};

export function Toast({ tone = "success", children }: { tone?: Tone; children: ReactNode }) {
  const t = tones[tone];
  return (
    <div
      role={t.role}
      className={cn(
        "pointer-events-auto max-w-sm rounded-md px-4 py-3 text-body shadow-2",
        "transition-opacity duration-slow ease-standard",
        t.bg,
      )}
    >
      {children}
    </div>
  );
}
