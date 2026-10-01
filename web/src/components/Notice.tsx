import type { ReactNode } from "react";

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
 * left bar. Announced politely when it appears.
 */
export function Notice({ tone, label, children }: NoticeProps) {
  return (
    <div
      role="status"
      className={`flex flex-col gap-2 rounded-md border bg-surface p-4 ${BORDER[tone]}`}
    >
      <p className={`text-label ${LABEL[tone]}`}>{label}</p>
      <div className="max-w-reading-max text-body text-ink">{children}</div>
    </div>
  );
}
