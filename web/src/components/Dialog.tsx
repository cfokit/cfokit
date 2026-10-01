import { useEffect, useId, useRef, type ReactNode } from "react";

interface DialogProps {
  open: boolean;
  /** Called when the person dismisses it: Escape, or an action that closes it. */
  onClose: () => void;
  title: string;
  children: ReactNode;
  /** The dialog's buttons, the primary one last. */
  actions: ReactNode;
}

/**
 * A modal question. A `surface` panel with `radius-lg` and `shadow-overlay`, centered; below
 * `bp-tablet`, a sheet rising from the bottom edge, full width, with its actions in thumb reach.
 *
 * The browser's own `<dialog>` gives focus containment, Escape and the inert page behind it.
 * Radix's dialog would too, but locks scrolling by injecting a `<style>` element, which the
 * client's CSP refuses (ADR-0049 § 6); index.css locks it instead.
 */
export function Dialog({ open, onClose, title, children, actions }: DialogProps) {
  const ref = useRef<HTMLDialogElement>(null);
  const titleId = useId();

  useEffect(() => {
    const dialog = ref.current;
    if (dialog === null) return;
    if (open && !dialog.open) dialog.showModal();
    if (!open && dialog.open) dialog.close();
  }, [open]);

  return (
    <dialog
      ref={ref}
      aria-labelledby={titleId}
      onClose={onClose}
      className={[
        "mx-0 mt-auto mb-0 w-full max-w-none rounded-t-lg bg-surface p-6 text-ink shadow-overlay",
        "tablet:m-auto tablet:max-w-reading-max tablet:rounded-lg",
        "backdrop:bg-ink/40",
      ].join(" ")}
    >
      <div className="flex flex-col gap-6">
        <h2 id={titleId} className="font-display text-heading-compact text-ink tablet:text-heading">
          {title}
        </h2>
        <div className="text-body">{children}</div>
        <div className="flex flex-col-reverse gap-3 tablet:flex-row tablet:justify-end">
          {actions}
        </div>
      </div>
    </dialog>
  );
}
