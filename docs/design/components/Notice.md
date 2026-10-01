# Notice

A panel that says what happened or what to know, with a leading word that carries the state.

- `tone="success"`: agrees, finished ("Matches", "Imported").
- `tone="warning"`: look, but not wrong ("Expected difference").
- `tone="danger"`: refused, failed ("Refused", "Differs").
- `tone="neutral"`: information with no state ("Safe to leave").

A 1px border in the state's colour and the `label` word in that colour; the body is `ink`. Nothing
depends on telling colours apart, and there is no coloured left bar. Errors say what went wrong and
what to do, without apology.

Pass `announce` when the notice appears in response to something, such as a refusal after an upload,
so screen readers read it. Leave it off for a notice that is part of the page as it loads.

Props: `tone`, `label`, `children`, `announce`.

```html
<x-import component-from-global-scope="CFOKit.Notice" tone="warning" label="Expected difference">Balances that depend on the basis differ.</x-import>
```
