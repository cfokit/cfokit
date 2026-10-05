/**
 * Writes the synthetic QuickBooks export as a .zip a person can choose on the getting-started
 * page — the same file the end-to-end test imports, from the same rows the reader's tests check
 * (`src/quickbooks/synthetic.ts`), so there is one source and nothing binary is committed.
 *
 *     pnpm sample-export                 # writes ../.local/quickbooks-sample.zip
 *     pnpm sample-export ~/Downloads/x.zip
 */

import { mkdir, writeFile } from "node:fs/promises";
import { dirname, resolve } from "node:path";
import { syntheticExport } from "../src/quickbooks/synthetic.ts";

const target = resolve(process.argv[2] ?? "../.local/quickbooks-sample.zip");
await mkdir(dirname(target), { recursive: true });
await writeFile(target, await syntheticExport());
console.log(`Wrote ${target}`);
