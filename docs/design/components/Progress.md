# Progress

Work that takes more than a few seconds: an `accent` bar on `sunken` with the count beside it, "2,140 of 5,553 transactions".

Never a spinner alone. Put a `caption` under it when the wait is long ("This can take several
minutes."), and a neutral `Notice` when it is safe to leave. `value` and `max` are counts, not money.

Props: `value`, `max`, `unit` (plural: "transactions"), `label` (what the bar measures, for screen
readers).

```html
<x-import component-from-global-scope="CFOKit.Progress" value="{{2140}}" max="{{5553}}" unit="transactions" label="Import progress"></x-import>
```
