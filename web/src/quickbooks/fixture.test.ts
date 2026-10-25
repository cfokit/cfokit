// @vitest-environment node
/**
 * The QuickBooks fixture through the reader that ships (ADR-0079).
 *
 * Each archive in `tests/fixtures/quickbooks/archives/` is read and its reading compared with the
 * `read.json` committed beside it, which the round trip into CFOKit imports. That comparison holds
 * the readings current and asserts nothing about whether they are right: the round trip does, in
 * the integration suite, against figures QuickBooks agreed with. `pnpm read-fixture` writes them.
 *
 * The file cases are checked here, because a damaged file is the reader's to refuse: each
 * mutation of the accrual archive is refused with the code its catalog case names, or read just as
 * the undamaged archive is.
 */
import { readdir, readFile } from "node:fs/promises";
import { MUTATIONS } from "./mutations";
import { read, type Export } from "./read";
import { Refused } from "./refused";

const FIXTURE = new URL("../../../tests/fixtures/quickbooks/", import.meta.url);

type Reading = Export | { refused: { code: string; detail: string } };

interface Case {
  category: string;
  check: { kind: string; code?: string };
  mutation?: string;
}

async function archive(rendering: string): Promise<Uint8Array> {
  return new Uint8Array(await readFile(new URL(`archives/${rendering}/export.zip`, FIXTURE)));
}

async function reading(bytes: Uint8Array): Promise<Reading> {
  try {
    return await read(bytes);
  } catch (error) {
    if (error instanceof Refused) return { refused: { code: error.code, detail: error.message } };
    throw error;
  }
}

/**
 * A reading as JSON a review can take in: the shape's fields one to a line, and each account,
 * entry and stated balance on a line of its own.
 */
function written(value: unknown, depth = 0): string {
  const pad = " ".repeat(depth + 1);
  if (Array.isArray(value) && depth <= 2 && value.length > 0) {
    const items = value.map((item) => pad + JSON.stringify(item));
    return `[\n${items.join(",\n")}\n${" ".repeat(depth)}]`;
  }
  if (value !== null && typeof value === "object" && !Array.isArray(value) && depth < 2) {
    const fields = Object.entries(value).map(
      ([key, item]) => `${pad}${JSON.stringify(key)}: ${written(item, depth + 1)}`,
    );
    return `{\n${fields.join(",\n")}\n${" ".repeat(depth)}}`;
  }
  return JSON.stringify(value);
}

const renderings = (await readdir(new URL("archives/", FIXTURE))).sort();
const manifest = JSON.parse(
  await readFile(new URL("generated/manifest.json", FIXTURE), "utf8"),
) as { cases: Record<string, Case> };
const fileCases = Object.entries(manifest.cases).filter(([, entry]) => entry.category === "file");

describe("each archive's reading", () => {
  test.each(renderings)("%s is what the reader reads", async (rendering) => {
    const path = `../../../tests/fixtures/quickbooks/archives/${rendering}/read.json`;
    await expect(written(await reading(await archive(rendering))) + "\n").toMatchFileSnapshot(path);
  });
});

describe("the file cases", () => {
  test("every file case has a mutation, and every mutation a case", () => {
    expect(Object.keys(MUTATIONS).sort()).toEqual(fileCases.map(([id]) => id).sort());
  });

  test.each(fileCases)("%s is read as its case says", async (id, entry) => {
    const accrual = await archive("accrual");
    const mutate = MUTATIONS[id];
    if (mutate === undefined) throw new Error(`${id} has no mutation`);
    const damaged = await reading(await mutate(accrual));
    if (entry.check.kind === "refused") {
      expect(damaged).toMatchObject({ refused: { code: entry.check.code } });
      return;
    }
    // Read as the undamaged archive is, but for the fingerprint, which is of the file's bytes.
    const undamaged = (await reading(accrual)) as Export;
    expect("refused" in damaged ? damaged.refused : null).toBeNull();
    const books = { ...(damaged as Export).books, fingerprint: undamaged.books.fingerprint };
    expect({ ...(damaged as Export), books }).toEqual(undamaged);
  });
});
