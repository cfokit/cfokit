import { formatMoney } from "./formatMoney";

interface MoneyProps {
  /** A signed decimal string, as the API sends it. */
  amount: string;
  /** The commodity's display scale (ADR-0025). */
  scale?: number;
  /** `total` for a total or headline figure the API computed; never one summed on the page. */
  variant?: "amount" | "total";
  className?: string;
}

/**
 * An amount, in tabular figures, with a negative in parentheses: the accounting convention, and
 * never shown by color alone. A positive amount keeps an invisible closing parenthesis so the
 * digits of a column line up. Screen readers hear "minus" rather than the parentheses; the
 * figure is its own positioning context, so that hidden word stays inside a scrolling table.
 */
export function Money({ amount, scale, variant = "amount", className }: MoneyProps) {
  const { negative, digits } = formatMoney(amount, scale);
  const size =
    variant === "total" ? "text-money-total-compact tablet:text-money-total" : "text-money";
  return (
    <span
      className={["relative whitespace-nowrap tabular-nums", size, className]
        .filter(Boolean)
        .join(" ")}
    >
      {negative ? (
        <>
          <span aria-hidden="true">(</span>
          <span className="sr-only">minus </span>
          {digits}
          <span aria-hidden="true">)</span>
        </>
      ) : (
        <>
          {digits}
          <span aria-hidden="true" className="invisible">
            )
          </span>
        </>
      )}
    </span>
  );
}
