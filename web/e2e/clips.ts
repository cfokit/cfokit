/**
 * A recorded run, cut into one clip per step (ADR-0074 § 3). The reporter keeps where each
 * top-level `test.step` began and ended in a passing run's video; `cut-clips.ts` cuts each one
 * into an MP4, a still of how it leaves the screen, and a WebVTT caption track whose cue is the
 * step's title.
 */

export interface Clip {
  /** The step's place in the run, from 1. */
  index: number;
  /** The step's title, which is the clip's caption. */
  title: string;
  /** Seconds into the run's video. */
  start: number;
  end: number;
}

/** What the reporter writes for one passing run, and the cutter reads. */
export interface Recording {
  /** The recorded flow's name, the spec's file name without `.spec.ts`: `onboarding`. */
  name: string;
  video: string;
  clips: Clip[];
}

export interface RecordedStep {
  title: string;
  startTime: Date;
  duration: number;
}

// Starting each clip this much before its step keeps the step's first frame in it.
const LEAD_IN = 0.5;

/** Each step's span in the video, in seconds from when the video began: when the page opened. */
export function clipsOf(videoStart: Date, steps: RecordedStep[]): Clip[] {
  return steps.map((step, i) => {
    const from = (step.startTime.getTime() - videoStart.getTime()) / 1000;
    return {
      index: i + 1,
      title: step.title,
      start: Math.max(0, from - LEAD_IN),
      end: from + step.duration / 1000,
    };
  });
}

/** The file name a clip is published under, without its extension: `onboarding-01-sign-up`. */
export function clipName(recording: string, clip: Clip): string {
  const slug = clip.title
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
  return `${recording}-${String(clip.index).padStart(2, "0")}-${slug}`;
}

/** A WebVTT timestamp, `hh:mm:ss.ttt`. */
function timestamp(seconds: number): string {
  const ms = Math.round(seconds * 1000);
  const hh = String(Math.floor(ms / 3_600_000)).padStart(2, "0");
  const mm = String(Math.floor(ms / 60_000) % 60).padStart(2, "0");
  const ss = String(Math.floor(ms / 1000) % 60).padStart(2, "0");
  return `${hh}:${mm}:${ss}.${String(ms % 1000).padStart(3, "0")}`;
}

/** A caption track for one clip: its title, for the whole clip. */
export function captions(clip: Clip): string {
  return `WEBVTT\n\n${timestamp(0)} --> ${timestamp(clip.end - clip.start)}\n${clip.title}\n`;
}
