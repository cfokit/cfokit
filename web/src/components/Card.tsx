import type { ReactNode } from "react";

interface CardProps {
  /** The card's title, as a heading in `title` style. */
  title?: string;
  children: ReactNode;
}

/**
 * An object that stands apart from the page: a form panel, the sign-in card. Lists of rows are
 * tables, not cards.
 */
export function Card({ title, children }: CardProps) {
  return (
    <section className="flex flex-col gap-4 rounded-lg border border-rule bg-surface p-6">
      {title !== undefined && <h2 className="text-title text-ink">{title}</h2>}
      {children}
    </section>
  );
}
