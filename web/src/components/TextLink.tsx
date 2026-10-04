import type { ComponentProps } from "react";

/**
 * A link that goes somewhere, such as "Forgot your password?" or "Create an account", in the
 * `link` button's look. An action on this page is a `Button`; a link leaves it.
 */
export function TextLink({ className, ...props }: ComponentProps<"a">) {
  return (
    <a
      className={[
        "text-body text-accent underline underline-offset-3 hover:text-accent-hover",
        className,
      ]
        .filter(Boolean)
        .join(" ")}
      {...props}
    />
  );
}
