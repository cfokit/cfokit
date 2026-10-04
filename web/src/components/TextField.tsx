import { useId, type ComponentProps } from "react";

interface TextFieldProps extends Omit<ComponentProps<"input">, "id" | "className"> {
  /** What the field is, above it, in sentence case. */
  label: string;
  /** Help text below the input: the one-line explanation of an accounting term goes here. */
  help?: string;
  /** What is wrong and what to do, shown below the input and announced with it. */
  error?: string;
}

/**
 * A labeled text input. Typed text is `input` size (16px) on every device, because iOS Safari
 * zooms into anything smaller. Pass `inputMode` and `autoComplete` so a phone shows the right
 * keyboard: `inputMode="decimal"` for an amount, `type="email"` for an email.
 */
export function TextField({ label, help, error, ...input }: TextFieldProps) {
  const id = useId();
  const helpId = help === undefined ? undefined : `${id}-help`;
  const errorId = error === undefined ? undefined : `${id}-error`;
  const describedBy = [helpId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={id} className="text-label text-ink">
        {label}
      </label>
      <input
        id={id}
        aria-describedby={describedBy}
        aria-invalid={error === undefined ? undefined : true}
        className={[
          "min-h-target-min w-full rounded-sm border bg-surface px-3 text-input text-ink",
          error === undefined ? "border-control-border" : "border-danger",
        ].join(" ")}
        {...input}
      />
      {help !== undefined && (
        <p id={helpId} className="text-caption text-ink-muted">
          {help}
        </p>
      )}
      {error !== undefined && (
        <p id={errorId} className="text-caption text-danger">
          {error}
        </p>
      )}
    </div>
  );
}
