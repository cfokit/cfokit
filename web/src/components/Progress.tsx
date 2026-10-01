interface ProgressProps {
  /** How many are done. */
  value: number;
  /** How many there are in all. */
  max: number;
  /** What is being counted, plural: "transactions". */
  unit: string;
  /** What the bar measures, for screen readers: "Import progress". */
  label: string;
}

const grouped = new Intl.NumberFormat("en-US");

/**
 * Work that takes more than a few seconds: an `accent` bar on `sunken` with the count beside it,
 * "2,140 of 5,553 transactions". Never a spinner alone. These are counts, not money.
 */
export function Progress({ value, max, unit, label }: ProgressProps) {
  const done = Math.min(Math.max(value, 0), max);
  const percent = max === 0 ? 0 : (done / max) * 100;
  return (
    <div className="flex flex-col gap-2">
      <div
        role="progressbar"
        aria-label={label}
        aria-valuemin={0}
        aria-valuemax={max}
        aria-valuenow={done}
        aria-valuetext={`${grouped.format(done)} of ${grouped.format(max)} ${unit}`}
        className="h-2 overflow-hidden rounded-sm bg-sunken"
      >
        <div className="h-full bg-accent" style={{ width: `${percent}%` }} />
      </div>
      <p className="text-money text-ink tabular-nums">
        {grouped.format(done)} of {grouped.format(max)} {unit}
      </p>
    </div>
  );
}
