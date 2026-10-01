import { formatMoney } from "./formatMoney";

// Expected values come from the contract's own examples, the design system's README and the
// rounding rule ADR-0025 and RPT-12 state, not from running the formatter.

test.each([
  // The examples docs/contracts/openapi.json gives for every signed amount.
  ["100.00", false, "100.00"],
  ["-1250.5000000000", true, "1,250.50"],
  // The README's money sample: "(1,250.00)".
  ["-1250", true, "1,250.00"],
  // Half-up at the display scale, ties away from zero (ADR-0025, RPT-12).
  ["2.345", false, "2.35"],
  ["-2.345", true, "2.35"],
  ["2.3449999999", false, "2.34"],
  ["0.005", false, "0.01"],
  // Zero has no sign, however it was reached.
  ["-0.004", false, "0.00"],
  ["0", false, "0.00"],
  // Grouping in thousands, as the canvas's figures show ("5,553", "25,469.00").
  ["25469", false, "25,469.00"],
  ["1234567.891", false, "1,234,567.89"],
  ["999.995", false, "1,000.00"],
])("%s shows as negative=%s, %s", (amount, negative, digits) => {
  expect(formatMoney(amount)).toEqual({ negative, digits });
});

test("a commodity with a display scale of 0 shows whole units (ADR-0025: JPY 0)", () => {
  expect(formatMoney("1234.5", 0)).toEqual({ negative: false, digits: "1,235" });
});

test("a commodity with a display scale of 3 keeps three places (ADR-0025)", () => {
  expect(formatMoney("-0.0005", 3)).toEqual({ negative: true, digits: "0.001" });
});

test("an amount that is not a decimal string is refused, not shown as something else", () => {
  expect(() => formatMoney("1,250.00")).toThrow();
  expect(() => formatMoney("")).toThrow();
});
