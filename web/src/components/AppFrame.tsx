import { useEffect, useId, useState, type ReactNode } from "react";
import mark from "../design/brand/cfokit-mark.svg";
import markDark from "../design/brand/cfokit-mark-dark.svg";
import { Button } from "./Button";

interface AppFrameProps {
  /** The company whose books these are, shown beside the mark. */
  company: string;
  /** The signed-in person's name. */
  person: string;
  onSignOut: () => void;
  children: ReactNode;
}

/**
 * The frame every signed-in page sits in: a `bar-height` header on `surface` with the mark and
 * the company's name at the left and the person with "Sign out" at the right; below `bp-tablet`
 * those two move into a menu. The header adds the device's safe-area inset, so nothing sits under
 * a notch. Content is centered and stops widening at `content-max`. Sign-in screens have no frame.
 */
export function AppFrame({ company, person, onSignOut, children }: AppFrameProps) {
  const [menuOpen, setMenuOpen] = useState(false);
  const menuId = useId();

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [menuOpen]);

  return (
    <div className="flex min-h-dvh flex-col">
      <header className="sticky top-0 z-10 border-b border-rule bg-surface pt-safe">
        <div className="mx-auto flex h-bar-height max-w-content-max items-center justify-between gap-4 pr-2 pl-gutter-phone tablet:px-gutter-tablet desktop:px-gutter-desktop">
          <div className="flex min-w-0 items-center gap-3">
            <picture className="shrink-0">
              <source srcSet={markDark} media="(prefers-color-scheme: dark)" />
              <img src={mark} alt="CFOKit" width={24} height={24} className="size-6" />
            </picture>
            <span className="truncate text-title text-ink">{company}</span>
          </div>
          <div className="hidden shrink-0 items-center gap-2 tablet:flex">
            <span className="text-body text-ink">{person}</span>
            <Button variant="link" onClick={onSignOut}>
              Sign out
            </Button>
          </div>
          <div className="tablet:hidden">
            <Button
              variant="link"
              aria-expanded={menuOpen}
              aria-controls={menuId}
              onClick={() => setMenuOpen((open) => !open)}
            >
              Account
            </Button>
          </div>
        </div>
        {menuOpen && (
          <div
            id={menuId}
            className="flex items-center justify-between gap-4 border-t border-rule px-gutter-phone py-2 tablet:hidden"
          >
            <span className="truncate text-body text-ink">{person}</span>
            <Button variant="link" onClick={onSignOut}>
              Sign out
            </Button>
          </div>
        )}
      </header>
      <main className="mx-auto w-full max-w-content-max flex-1 px-gutter-phone py-6 tablet:px-gutter-tablet tablet:py-10 desktop:px-gutter-desktop">
        {children}
      </main>
    </div>
  );
}
