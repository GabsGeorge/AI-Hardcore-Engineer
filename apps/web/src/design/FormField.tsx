import { useId, type ReactNode } from "react";
import { Label } from "./Label";
import { cn } from "./cn";

type ChildRender = (ids: { input: string; help: string; error: string }) => ReactNode;

export function FormField({
  label,
  required,
  help,
  error,
  children,
  className,
}: {
  label: string;
  required?: boolean;
  help?: string;
  error?: string;
  children: ChildRender;
  className?: string;
}) {
  const inputId = useId();
  const helpId = useId();
  const errorId = useId();
  const isError = Boolean(error);
  return (
    <div className={cn("flex flex-col gap-1", className)}>
      <Label htmlFor={inputId} required={required}>
        {label}
      </Label>
      {children({ input: inputId, help: helpId, error: errorId })}
      {isError ? (
        <p id={errorId} className="text-label text-state-danger" role="alert">
          {error}
        </p>
      ) : help ? (
        <p id={helpId} className="text-label text-ink-400">
          {help}
        </p>
      ) : null}
    </div>
  );
}
