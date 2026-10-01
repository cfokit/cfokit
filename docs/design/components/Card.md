# Card

An object that stands apart from the page: a form panel, a dialog's content, the sign-in card.

`surface`, `radius-lg`, a `rule` border, `space-6` padding, and an optional `title` in `title`. Use
it sparingly: lists of rows are tables, not cards, and the page itself sits on `paper`.

Props: `title`, `children`.

```html
<x-import component-from-global-scope="CFOKit.Card" title="Your company">…</x-import>
```
