import type { ComponentProps } from "react";

type Variant = "primary" | "secondary" | "destructive" | "link";

interface ButtonProps extends ComponentProps<"button"> {
  /**
   * `primary`: the one main action on a screen. `secondary`: every other action.
   * `destructive`: an action that removes or abandons something, in danger text, never filled.
   * `link`: an action that reads as a link, such as "Sign out".
   */
  variant?: Variant;
  /** Spans its container, as the primary action does in the bottom action bar on a phone. */
  fullWidth?: boolean;
}

const VARIANTS: Record<Variant, string> = {
  primary:
    "rounded-md border border-accent bg-accent px-6 font-semibold text-on-accent hover:border-accent-hover hover:bg-accent-hover",
  secondary:
    "rounded-md border border-control-border bg-surface px-6 font-semibold text-ink hover:bg-sunken",
  destructive:
    "rounded-md border border-control-border bg-surface px-6 font-semibold text-danger hover:bg-sunken",
  link: "px-3 text-accent underline underline-offset-3 hover:text-accent-hover",
};

/** A button, at least `target-min` tall on every device, in sentence case. */
export function Button({
  variant = "secondary",
  fullWidth = false,
  type = "button",
  className,
  ...props
}: ButtonProps) {
  return (
    <button
      type={type}
      className={[
        "inline-flex min-h-target-min cursor-pointer items-center justify-center gap-2 text-body",
        "disabled:cursor-not-allowed disabled:opacity-60",
        VARIANTS[variant],
        fullWidth ? "w-full" : "",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...props}
    />
  );
}
