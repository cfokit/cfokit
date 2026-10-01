import { useEffect, useState, type ReactNode } from "react";

type Tone = "neutral" | "success" | "warning" | "danger";

interface NoticeProps {
  /**
   * `success`: agrees, finished. `warning`: look, but not wrong. `danger`: refused, failed.
   * `neutral`: information with no state, such as "Safe to leave".
   */
  tone: Tone;
  /** The leading word or phrase, in the tone's color: "Refused", "Expected difference". */
  label: string;
  children: ReactNode;
  /**
   * Announce the notice to screen readers when it appears, as for a refusal after an upload.
   * Leave it off for a notice that is part of the page as it loads, which is read in its place.
   */
  announce?: boolean;
}

const BORDER: Record<Tone, string> = {
  neutral: "border-control-border",
  success: "border-success",
  warning: "border-warning",
  danger: "border-danger",
};

const LABEL: Record<Tone, string> = {
  neutral: "text-ink",
  success: "text-success",
  warning: "text-warning",
  danger: "text-danger",
};

/**
 * A panel that says what happened or what to know, with a 1px border in the state's color and a
 * leading word that carries the state, so nothing depends on telling colors apart. No colored
 * left bar.
 *
 * Screen readers announce a change inside a live region already on the page, not a region that
 * arrives with its text, so an announced notice puts its region in place empty and fills it a
 * moment later.
 */
export function Notice({ tone, label, children, announce = false }: NoticeProps) {
  const [filled, setFilled] = useState(!announce);

  useEffect(() => {
    if (filled) return;
    const timer = setTimeout(() => setFilled(true), 0);
    return () => clearTimeout(timer);
  }, [filled]);

  return (
    <div
      role={announce ? "status" : undefined}
      className={`flex flex-col gap-2 rounded-md border bg-surface p-4 ${BORDER[tone]}`}
    >
      {filled && (
        <>
          <p className={`text-label ${LABEL[tone]}`}>{label}</p>
          <div className="max-w-reading-max text-body text-ink">{children}</div>
        </>
      )}
    </div>
  );
}
