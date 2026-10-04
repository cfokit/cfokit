# CopyBlock

Text the person copies somewhere else — a prompt to paste into Claude, a command, a configuration —
on `sunken` with a `rule` border, its `label` above it and a "Copy" link-style button at the right
that reads "Copied" once it has.

The text is shown exactly, line breaks kept, and wraps rather than scrolling sideways. It stays
selectable, so a browser that refuses the clipboard still lets the person copy it by hand. Never use
it for figures from the books: those are `Money` and `MoneyTable`.

Props: `label` (what the text is, in sentence case), `text`.

```html
<x-import
  component-from-global-scope="CFOKit.CopyBlock"
  label="Your first question"
  text="My books are imported into CFOKit. Confirm they match QuickBooks and explain any differences."
></x-import>
```
