/**
 * Keeps where each top-level `test.step` of a passing, recorded test began and ended, in
 * `test-results/clips/<name>.json`, for `cut-clips.ts` (ADR-0074 § 3). A failed run keeps
 * nothing, so nothing is cut from it.
 */

import { mkdirSync, writeFileSync } from "node:fs";
import { basename, join } from "node:path";
import type { Reporter, TestCase, TestResult, TestStep } from "@playwright/test/reporter";
import { clipsOf, type Recording } from "./clips.ts";

const OUT = "test-results/clips";

// The page's video begins when the page fixture opens it, which is up to a second or more after
// the test starts while the browser launches.
function pageOpened(steps: TestStep[]): Date | undefined {
  for (const step of steps) {
    if (step.category === "fixture" && step.title === 'Fixture "page"') return step.startTime;
    const inner = pageOpened(step.steps);
    if (inner) return inner;
  }
  return undefined;
}

export default class ClipsReporter implements Reporter {
  onTestEnd(test: TestCase, result: TestResult): void {
    const video = result.attachments.find((a) => a.name === "video")?.path;
    const steps = result.steps.filter((step) => step.category === "test.step");
    if (result.status !== "passed" || !video || steps.length === 0) return;

    const recording: Recording = {
      name: basename(test.location.file, ".spec.ts"),
      video,
      clips: clipsOf(pageOpened(result.steps) ?? result.startTime, steps),
    };
    mkdirSync(OUT, { recursive: true });
    writeFileSync(join(OUT, `${recording.name}.json`), JSON.stringify(recording, null, 2));
  }
}
