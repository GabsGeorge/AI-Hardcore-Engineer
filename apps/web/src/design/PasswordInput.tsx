import { useState, type InputHTMLAttributes } from "react";
import { Input } from "./Input";
import { cn } from "./cn";

/** Password input with a show / hide toggle. The toggle is a text button, not an icon only. */
export function PasswordInput({
  invalid,
  className,
  ...rest
}: { invalid?: boolean } & InputHTMLAttributes<HTMLInputElement>) {
  const [visible, setVisible] = useState(false);
  return (
    <div className={cn("relative", className)}>
      <Input {...rest} type={visible ? "text" : "password"} invalid={invalid} className="pr-16" />
      <button
        type="button"
        onClick={() => setVisible((v) => !v)}
        className={cn(
          "absolute inset-y-0 right-0 flex items-center px-3 text-label text-ink-500",
          "hover:text-ink-700 focus-visible:outline-none focus-visible:ring-2",
          "focus-visible:ring-support focus-visible:ring-offset-2 focus-visible:ring-offset-page",
          "rounded-r-md",
        )}
        aria-pressed={visible}
      >
        {visible ? "ocultar" : "mostrar"}
      </button>
    </div>
  );
}
