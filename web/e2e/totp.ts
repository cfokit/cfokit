/**
 * The code an authenticator app shows, so the end-to-end test can set up and use a second factor
 * the way a person does. RFC 6238 over RFC 4226, with the issuer's defaults: HMAC-SHA1, six digits,
 * a thirty-second step. Node's own crypto, so no dependency for twenty lines.
 */

import { createHmac } from "node:crypto";

const ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";

/** The key as the issuer shows it: RFC 4648 base32, in groups, padding optional. */
function base32(encoded: string): Buffer {
  const clean = encoded.replace(/[\s=]/g, "").toUpperCase();
  let bits = 0;
  let value = 0;
  const bytes: number[] = [];
  for (const char of clean) {
    const index = ALPHABET.indexOf(char);
    if (index < 0) throw new Error(`not base32: ${char}`);
    value = (value << 5) | index;
    bits += 5;
    if (bits >= 8) {
      bytes.push((value >>> (bits - 8)) & 0xff);
      bits -= 8;
    }
  }
  return Buffer.from(bytes);
}

export function totp(encodedKey: string, at: number = Date.now(), step = 30, digits = 6): string {
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(at / 1000 / step)));
  const mac = createHmac("sha1", base32(encodedKey)).update(counter).digest();
  const offset = mac.readUInt8(mac.length - 1) & 0x0f;
  const code = (mac.readUInt32BE(offset) & 0x7fffffff) % 10 ** digits;
  return code.toString().padStart(digits, "0");
}
