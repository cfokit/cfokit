# MoneyTable

Rows of figures: `label` headers on `sunken`, rows divided by `rule`, amounts right-aligned, and totals from the API beneath.

The first column names the row. The currency is shown once, in each money column's header. A
`flagged` row gets an `ochre` tick: the one the reader should look at next, such as an account that
differs. Totals are the API's, never summed on the page. Lists of rows are tables, not cards.

Below `bp-tablet`, a table with one or two figures per row becomes a list: the row's name on one
line, its other text in `caption`, and its figures beside it or labelled beneath. A wider table keeps
its columns and scrolls sideways within its own frame, first column fixed; the page never scrolls
sideways.

Props: `caption`, `currency`, `columns` (`{key, header, kind: "text" | "money"}`), `rows`
(`{id, cells: {key: string}, flagged?}`), `totals` (by money column key), `scale`.

```html
<x-import component-from-global-scope="CFOKit.MoneyTable" caption="Balances" currency="USD" columns="{{columns}}" rows="{{rows}}" totals="{{totals}}"></x-import>
```
