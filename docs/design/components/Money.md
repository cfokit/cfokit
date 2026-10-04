# Money

One amount: tabular figures, rounded half-up to its display scale once, grouped in thousands, a negative in parentheses.

`amount` is the decimal string the API sends ("-1250.5000000000"), never a number, and never one
summed on the page. A negative shows as (1,250.50), never by color alone and never in red; screen
readers hear "minus". `variant="total"` is for a total or headline figure the API computed, in
`money-total`. Show the currency once, in a column header or beside a total, not on every figure.

Props: `amount`, `scale` (decimal places; 2 unless the currency says otherwise), `variant`
(`amount` or `total`).

```html
<x-import component-from-global-scope="CFOKit.Money" amount="-1250.00"></x-import>
```
