# Dialog

A modal question: a `surface` panel with `radius-lg` and `shadow-overlay`, centred; on a phone, a sheet rising from the bottom edge with its actions in thumb reach.

The title is a question; the actions say what each does ("Keep importing", "Stop the import"), the
primary one last. Escape and the actions close it. The page behind is held still and dimmed.

Props: `open`, `onClose`, `title`, `children`, `actions` (its buttons).

```html
<x-import component-from-global-scope="CFOKit.Dialog" open="{{yes}}" title="Stop the import?" actions="{{actions}}">The transactions imported so far stay.</x-import>
```
