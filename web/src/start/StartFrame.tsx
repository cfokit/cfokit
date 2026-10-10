import type { ReactNode } from "react";
import { StepIndicator } from "../components";
import { PersonFrame } from "../settings/PersonFrame";
import { useStarted } from "./state";

/** The steps of getting started (ADR-0058 § 1), after the account is made. */
export const STEPS = ["Your export", "Your company", "Import", "Connect Claude", "First question"];

interface StartFrameProps {
  /** The index of this page's step in `STEPS`. */
  step: number;
  title: string;
  children: ReactNode;
}

/** A page of getting started: the app frame, where the person is, and the step's heading. */
export function StartFrame({ step, title, children }: StartFrameProps) {
  const { company } = useStarted();
  return (
    <PersonFrame company={company}>
      <div className="flex flex-col gap-6 tablet:flex-row tablet:gap-10">
        <div className="tablet:shrink-0">
          <StepIndicator steps={STEPS} current={step} label="Getting started" />
        </div>
        <div className="flex max-w-reading-max min-w-0 flex-1 flex-col gap-6">
          <h1 className="font-display text-display-compact text-ink tablet:text-display">
            {title}
          </h1>
          {children}
        </div>
      </div>
    </PersonFrame>
  );
}
