import type { ReactNode } from "react";

/**
 * A screen's actions. Below `bp-tablet` they sit in a bar pinned to the bottom of the screen, in
 * thumb reach, above the home indicator; give the primary button `fullWidth` there. From
 * `bp-tablet` they sit inline after the content.
 */
export function ActionBar({ children }: { children: ReactNode }) {
  return (
    <>
      <div
        className={[
          "fixed inset-x-0 bottom-0 z-10 flex flex-col gap-3 border-t border-rule bg-surface px-4 pt-3 pb-safe",
          "tablet:static tablet:flex-row tablet:flex-wrap tablet:items-center tablet:border-0 tablet:bg-transparent tablet:p-0",
        ].join(" ")}
      >
        {children}
      </div>
      {/* Keeps the end of the page clear of the pinned bar on a phone. */}
      <div aria-hidden="true" className="h-bar-height tablet:hidden" />
    </>
  );
}
