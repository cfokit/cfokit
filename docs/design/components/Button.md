# Button

A button that says exactly what it does, in sentence case: "Import", "Create company", "Try another file".

- `variant="primary"`: the one main action on a screen. Never two.
- `variant="secondary"` (the default): every other action.
- `variant="destructive"`: removes or abandons something. Danger text on surface, never a filled red.
- `variant="link"`: an action that reads as a link, such as "Sign out" in the app frame.

Every button is at least `target-min` (44px) tall on every device. On a phone the primary action spans
the bottom action bar: give it `fullWidth` inside an `ActionBar`.

Props: `variant`, `fullWidth`, `disabled`, `type` (defaults to `button`, so it never submits unless
asked), `onClick`, and any other `<button>` attribute.

```html
<x-import component-from-global-scope="CFOKit.Button" variant="primary">Import</x-import>
```
