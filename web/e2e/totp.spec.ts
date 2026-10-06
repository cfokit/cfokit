/**
 * The authenticator-app codes the getting-started test computes, checked against RFC 6238's own
 * test vectors (Appendix B, SHA-1): the key is the ASCII "12345678901234567890", shown here in
 * base32 the way the issuer shows a key, and the codes are eight digits.
 */

import { expect, test } from "@playwright/test";
import { totp } from "./totp.ts";

const KEY = "GEZD GNBV GY3T QOJQ GEZD GNBV GY3T QOJQ";

test("codes match RFC 6238's SHA-1 test vectors", () => {
  const vectors: [number, string][] = [
    [59, "94287082"],
    [1111111109, "07081804"],
    [1111111111, "14050471"],
    [1234567890, "89005924"],
    [2000000000, "69279037"],
    [20000000000, "65353130"],
  ];
  for (const [seconds, code] of vectors) expect(totp(KEY, seconds * 1000, 30, 8)).toBe(code);
});
