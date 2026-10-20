/**
 * Cuts every passing recorded run into its clips, with ffmpeg (ADR-0074 § 3): for each run the
 * whole video as `<name>.mp4` and `<name>.gif`, and for each step `<name>-NN-<step>.mp4`, `.gif`
 * and `.vtt`.
 *
 *     node e2e/cut-clips.ts recording    # reads test-results/clips/, writes into recording/
 */

import { spawnSync } from "node:child_process";
import { mkdirSync, readdirSync, readFileSync, writeFileSync } from "node:fs";
import { join, resolve } from "node:path";
import { captions, clipName, type Recording } from "./clips.ts";

const SOURCE = "test-results/clips";
const target = resolve(process.argv[2] ?? "recording");

// An MP4 any browser plays, and a GIF small enough for a page to show inline.
const MP4 = ["-c:v", "libx264", "-pix_fmt", "yuv420p", "-movflags", "+faststart"];
const GIF = [
  "-vf",
  "fps=8,scale=800:-1:flags=lanczos,split[a][b];[a]palettegen[p];[b][p]paletteuse",
];

function ffmpeg(args: string[]): void {
  const run = spawnSync("ffmpeg", ["-loglevel", "error", "-y", ...args], { stdio: "inherit" });
  if (run.status !== 0) throw new Error(`ffmpeg ${args.join(" ")} exited ${run.status}`);
}

mkdirSync(target, { recursive: true });
for (const file of readdirSync(SOURCE).filter((f) => f.endsWith(".json"))) {
  const recording = JSON.parse(readFileSync(join(SOURCE, file), "utf8")) as Recording;
  ffmpeg(["-i", recording.video, ...MP4, join(target, `${recording.name}.mp4`)]);
  ffmpeg(["-i", recording.video, ...GIF, join(target, `${recording.name}.gif`)]);
  for (const clip of recording.clips) {
    const name = join(target, clipName(recording.name, clip));
    const span = ["-ss", clip.start.toFixed(3), "-to", clip.end.toFixed(3), "-i", recording.video];
    ffmpeg([...span, ...MP4, `${name}.mp4`]);
    ffmpeg([...span, ...GIF, `${name}.gif`]);
    writeFileSync(`${name}.vtt`, captions(clip));
  }
  console.log(`${recording.name}: the whole run and ${recording.clips.length} clips`);
}
