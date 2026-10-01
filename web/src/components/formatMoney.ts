import Big from "big.js";

// An amount as the API sends it, a signed decimal string at full precision, made ready to show:
// rounded half-up to the commodity's display scale, once, here at presentation, and grouped in
// thousands (ADR-0025, LED-06, RPT-12). It never becomes a JavaScript number (ADR-0005).
//
// The API does not yet send a commodity's display scale; until it does, callers pass it, and
// ADR-0025's default of 2 applies.
export interface Formatted {
  /** True for an amount below zero after rounding. A figure that rounds to zero has no sign. */
  negative: boolean;
  /** The magnitude, grouped and at the display scale: "1,250.50". */
  digits: string;
}

export function formatMoney(amount: string, scale = 2): Formatted {
  const rounded = new Big(amount).round(scale, Big.roundHalfUp);
  const negative = rounded.lt(0);
  const [whole = "", fraction] = rounded.abs().toFixed(scale).split(".");
  const grouped = whole.replace(/\B(?=(\d{3})+(?!\d))/g, ",");
  return { negative, digits: fraction === undefined ? grouped : `${grouped}.${fraction}` };
}
