import { useEffect, type ReactNode } from "react";
import lockup from "../../design/brand/cfokit-lockup.svg";
import lockupDark from "../../design/brand/cfokit-lockup-dark.svg";
import { Card, Notice } from "../components";
import type { KcContext } from "./KcContext";

type Message = NonNullable<KcContext["message"]>;

const TONE = {
  success: ["success", "Done"],
  warning: ["warning", "Check this"],
  error: ["danger", "Couldn't continue"],
  info: ["neutral", "Note"],
} as const satisfies Record<Message["type"], readonly [string, string]>;

/**
 * The issuer's messages are HTML: escaped text, and sometimes markup from its message bundles.
 * Only their text is kept, and it is rendered as text, never as markup (ADR-0049 § 6).
 */
export function plain(text: string): string {
  return new DOMParser().parseFromString(text, "text/html").documentElement.textContent;
}

interface SignInPageProps {
  /** The page's heading, which is also the document's title. */
  title: string;
  /** The issuer's message about the last step, unless the page shows it beside a field. */
  message?: Message | undefined;
  children: ReactNode;
}

/** A sign-in screen: no frame, the lockup above a single `Card` on `paper` (AppFrame.md). */
export function SignInPage({ title, message, children }: SignInPageProps) {
  useEffect(() => {
    document.title = `${title} · CFOKit`;
  }, [title]);

  return (
    <main className="mx-auto flex min-h-dvh max-w-reading-max flex-col gap-6 px-gutter-phone py-10 tablet:px-gutter-tablet">
      <picture className="self-center">
        <source srcSet={lockupDark} media="(prefers-color-scheme: dark)" />
        <img src={lockup} alt="CFOKit" width={203} height={48} />
      </picture>
      <Card>
        <h1 className="font-display text-heading-compact text-ink">{title}</h1>
        {message !== undefined && (
          <Notice tone={TONE[message.type][0]} label={TONE[message.type][1]} announce>
            {plain(message.summary)}
          </Notice>
        )}
        {children}
      </Card>
    </main>
  );
}
