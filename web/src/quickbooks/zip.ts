/**
 * Just enough of a zip reader for an accounting export, with bounds, because the archive is
 * somebody else's file (`NFR-04`).
 *
 * The browser inflates; this reads the directory and stops reading at the ceiling. Every size the
 * archive states about itself is a claim by whoever built it, so the directory is checked first —
 * metadata, no decompression — and every member's actual expansion is bounded again as it is read.
 */

import { Refused } from "./refused";

// Measured against a real export: eight members, 979,403 bytes expanded from 904,749, a ratio of
// 1.08. That ratio is structural rather than lucky — the members are `.xlsx` files, which are
// themselves zips — so a genuine export is very nearly incompressible and a high ratio is evidence
// the file is not one. These leave room for an export a hundred times larger.
export const MAX_ARCHIVE_BYTES = 100 * 1024 * 1024;
export const MAX_UNCOMPRESSED_BYTES = 300 * 1024 * 1024;
export const MAX_MEMBERS = 64;

const END_OF_DIRECTORY = 0x06054b50;
const DIRECTORY_ENTRY = 0x02014b50;
const LOCAL_HEADER = 0x04034b50;

interface Member {
  name: string;
  method: number;
  encrypted: boolean;
  compressedSize: number;
  size: number;
  offset: number;
}

export class Zip {
  private readonly members: Map<string, Member>;

  /** Reads the directory, refusing an archive that would expand past what this reads. */
  constructor(private readonly bytes: Uint8Array) {
    this.members = directory(bytes);
    if (this.members.size > MAX_MEMBERS) {
      throw new Refused(
        "import_too_large",
        `the archive holds ${this.members.size} members; this reads at most ${MAX_MEMBERS}`,
      );
    }
    let declared = 0;
    for (const member of this.members.values()) declared += member.size;
    if (declared > MAX_UNCOMPRESSED_BYTES) {
      throw new Refused(
        "import_too_large",
        `the archive declares ${declared} bytes expanded; this reads at most ${MAX_UNCOMPRESSED_BYTES}`,
      );
    }
  }

  has(name: string): boolean {
    return this.members.has(name);
  }

  /** One member's bytes, refusing to read past the ceiling whatever its entry declared. */
  async read(name: string): Promise<Uint8Array> {
    const member = this.members.get(name);
    if (member === undefined) throw new Refused("unreadable_archive", `${name} is missing`);
    if (member.encrypted) throw new Refused("unreadable_archive", `${name} is encrypted`);
    const view = new DataView(this.bytes.buffer, this.bytes.byteOffset, this.bytes.byteLength);
    if (
      member.offset + 30 > this.bytes.length ||
      view.getUint32(member.offset, true) !== LOCAL_HEADER
    ) {
      throw new Refused("unreadable_archive", `${name} has no local header`);
    }
    const start =
      member.offset +
      30 +
      view.getUint16(member.offset + 26, true) +
      view.getUint16(member.offset + 28, true);
    const data = this.bytes.subarray(start, start + member.compressedSize);
    if (member.method === 0) {
      if (data.length > MAX_UNCOMPRESSED_BYTES) throw tooLarge(name);
      return data;
    }
    if (member.method !== 8) {
      throw new Refused("unreadable_archive", `${name} uses compression method ${member.method}`);
    }
    return inflate(data, name);
  }
}

function tooLarge(name: string): Refused {
  return new Refused(
    "import_too_large",
    `${name} expands past ${MAX_UNCOMPRESSED_BYTES} bytes; the archive's own directory understated it`,
  );
}

async function inflate(data: Uint8Array, name: string): Promise<Uint8Array> {
  const stream = new Blob([data as Uint8Array<ArrayBuffer>])
    .stream()
    .pipeThrough(new DecompressionStream("deflate-raw"));
  const reader = stream.getReader();
  const chunks: Uint8Array[] = [];
  let total = 0;
  try {
    for (;;) {
      const { done, value } = await reader.read();
      if (done) break;
      total += value.length;
      if (total > MAX_UNCOMPRESSED_BYTES) {
        await reader.cancel();
        throw tooLarge(name);
      }
      chunks.push(value);
    }
  } catch (error) {
    if (error instanceof Refused) throw error;
    throw new Refused("unreadable_archive", `${name} could not be decompressed`);
  }
  const out = new Uint8Array(total);
  let at = 0;
  for (const chunk of chunks) {
    out.set(chunk, at);
    at += chunk.length;
  }
  return out;
}

function directory(bytes: Uint8Array): Map<string, Member> {
  const view = new DataView(bytes.buffer, bytes.byteOffset, bytes.byteLength);
  // The end record sits in the last 22 bytes, or up to 64 KB earlier behind a comment.
  let end = -1;
  for (let at = bytes.length - 22; at >= Math.max(0, bytes.length - 22 - 0xffff); at--) {
    if (view.getUint32(at, true) === END_OF_DIRECTORY) {
      end = at;
      break;
    }
  }
  if (end < 0) throw new Refused("unreadable_archive", "the file is not a zip archive");

  const count = view.getUint16(end + 10, true);
  let at = view.getUint32(end + 16, true);
  if (count === 0xffff || at === 0xffffffff) {
    throw new Refused(
      "unreadable_archive",
      "the archive is in the zip64 format, which no export uses",
    );
  }
  const names = new TextDecoder();
  const members = new Map<string, Member>();
  for (let i = 0; i < count; i++) {
    if (at + 46 > bytes.length || view.getUint32(at, true) !== DIRECTORY_ENTRY) {
      throw new Refused("unreadable_archive", "the archive's directory is damaged");
    }
    const nameLength = view.getUint16(at + 28, true);
    const name = names.decode(bytes.subarray(at + 46, at + 46 + nameLength));
    members.set(name, {
      name,
      encrypted: (view.getUint16(at + 8, true) & 1) === 1,
      method: view.getUint16(at + 10, true),
      compressedSize: view.getUint32(at + 20, true),
      size: view.getUint32(at + 24, true),
      offset: view.getUint32(at + 42, true),
    });
    at += 46 + nameLength + view.getUint16(at + 30, true) + view.getUint16(at + 32, true);
  }
  return members;
}
