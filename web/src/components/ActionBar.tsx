import { useLayoutEffect, useRef, useState, type ReactNode } from "react";

/**
 * A screen's actions. Below `bp-tablet` they sit in a bar pinned to the bottom of the screen, in
 * thumb reach, above the home indicator; give the primary button `fullWidth` there. From
 * `bp-tablet` they sit inline after the content.
 *
 * The pinned bar is as tall as its buttons and the device's inset make it, so the space it keeps
 * clear at the end of the page is measured from the bar rather than assumed.
 */
export function ActionBar({ children }: { children: ReactNode }) {
  const bar = useRef<HTMLDivElement>(null);
  const [height, setHeight] = useState(0);

  useLayoutEffect(() => {
    const element = bar.current;
    if (element === null) return;
    const measure = () => setHeight(element.offsetHeight);
    measure();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(measure);
    observer.observe(element);
    return () => observer.disconnect();
  }, []);

  return (
    <>
      <div
        ref={bar}
        className={[
          "fixed inset-x-0 bottom-0 z-10 flex flex-col gap-3 border-t border-rule bg-surface px-safe-4 pt-3 pb-safe-3",
          "tablet:static tablet:flex-row tablet:flex-wrap tablet:items-center tablet:border-0 tablet:bg-transparent tablet:p-0",
        ].join(" ")}
      >
        {children}
      </div>
      {/* Keeps the end of the page clear of the pinned bar on a phone. */}
      <div aria-hidden="true" className="tablet:hidden" style={{ height }} />
    </>
  );
}
