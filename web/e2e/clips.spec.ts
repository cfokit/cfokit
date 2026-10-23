/**
 * Cutting a recorded run into its steps' clips. A clip spans its step, starting half a second
 * early and never before the video does; the caption track is WebVTT as the W3C specification
 * writes it (https://www.w3.org/TR/webvtt1/, § 4.1): the `WEBVTT` line, a blank line, and a cue
 * timed `hh:mm:ss.ttt --> hh:mm:ss.ttt` followed by its text.
 */

import { expect, test } from "@playwright/test";
import { captions, clipName, clipsOf } from "./clips.ts";

const START = new Date("2026-10-20T12:00:00.000Z");
const at = (seconds: number) => new Date(START.getTime() + seconds * 1000);

test("each step is a clip of its own span, from half a second before it starts", () => {
  const clips = clipsOf(START, [
    { title: "Create your account", startTime: at(0.2), duration: 4_000 },
    { title: "Choose the export", startTime: at(10), duration: 2_500 },
  ]);
  expect(clips).toEqual([
    { index: 1, title: "Create your account", start: 0, end: 4.2 },
    { index: 2, title: "Choose the export", start: 9.5, end: 12.5 },
  ]);
});

test("a clip is named for its run, its place and its step", () => {
  const clip = { index: 3, title: "Confirm the company, then import", start: 0, end: 1 };
  expect(clipName("onboarding", clip)).toBe("onboarding-03-confirm-the-company-then-import");
});

test("the caption track is one cue, the step's title, for the whole clip", () => {
  const clip = { index: 1, title: "Connect Claude", start: 61.25, end: 3_725.5 };
  expect(captions(clip)).toBe("WEBVTT\n\n00:00:00.000 --> 01:01:04.250\nConnect Claude\n");
});
