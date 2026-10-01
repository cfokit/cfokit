import { CheckIcon } from "./icons";

interface StepIndicatorProps {
  /** The steps' names, in order, in sentence case. */
  steps: string[];
  /** The index of the current step. Those before it are done. */
  current: number;
  /** What the steps are: "Setup steps". */
  label: string;
}

/**
 * Where the person is in a sequence of steps. From `bp-tablet`, the whole list: done steps in
 * `ink-muted` with a check, the current one in `accent`, later ones numbered in `ink-muted`.
 * Below it, one line: "Step 2 of 4: Import your books".
 */
export function StepIndicator({ steps, current, label }: StepIndicatorProps) {
  return (
    <nav aria-label={label}>
      <p className="text-label text-ink-muted tablet:hidden">
        Step {current + 1} of {steps.length}: {steps[current]}
      </p>
      <ol className="hidden flex-col gap-1 tablet:flex">
        {steps.map((step, i) => {
          const done = i < current;
          const isCurrent = i === current;
          return (
            <li
              key={step}
              aria-current={isCurrent ? "step" : undefined}
              className={`flex min-h-10 items-center gap-2 text-label ${
                isCurrent ? "text-accent" : "text-ink-muted"
              }`}
            >
              {done ? (
                <CheckIcon />
              ) : (
                <span aria-hidden="true" className="w-4 text-center tabular-nums">
                  {i + 1}
                </span>
              )}
              <span>
                {step}
                {done && <span className="sr-only"> (done)</span>}
              </span>
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
