# DropZone

Where a file is chosen: one sentence and a "Choose file" button that opens the device's picker, with dropping a file as a shortcut beside it.

`sunken` fill, dashed `control-border`, `radius-md`. While a file is over it the border turns `accent`.
On a touch device there is nothing to drop, so the zone is only the "Choose file" button.

A file `accept` does not allow, dropped or picked, goes to `onReject` instead of `onFile`: show a
`Notice` with `tone="danger"`, `label="Refused"` and `announce`, saying what to choose instead.

Props: `prompt` (the sentence), `accept` (".zip"), `onFile`, `onReject`.

```html
<x-import component-from-global-scope="CFOKit.DropZone" prompt="Drop the QuickBooks export here, or choose it from your computer." accept=".zip"></x-import>
```
