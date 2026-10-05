# MoneyTable

Rows of figures: `label` headers on `sunken`, rows divided by `rule`, amounts right-aligned, and totals from the API beneath.

The first column names the row. The currency is shown once, in each money column's header. A
`flagged` row gets an `ochre` tick: the one the reader should look at next, such as an account that
differs. Totals are the API's, never summed on the page. Lists of rows are tables, not cards.

Below `bp-tablet`, a table with one or two figures per row becomes a list: the row's name on one
line, its other text in `caption`, and its figures beside it or labeled beneath. A wider table keeps
its columns and scrolls sideways within its own frame, first column fixed; the page never scrolls
sideways.

A row may carry an `action`, such as a `link` button that dismisses something about it. It sits
in a last column, headed for screen readers only, and beneath the row in the list. A table with
no actions has no such column.

Props: `caption`, `currency`, `columns` (`{key, header, kind: "text" | "money"}`), `rows`
(`{id, cells: {key: string}, flagged?, action?}`), `totals` (by money column key), `scale`,
`actionHeader` (the action column's screen-reader heading, "Actions" by default).

```html
<x-import
  component-from-global-scope="CFOKit.MoneyTable"
  caption="Balances"
  currency="USD"
  columns="{{columns}}"
  rows="{{rows}}"
  totals="{{totals}}"
></x-import>
```
