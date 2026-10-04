# TextField

A labeled text input, with optional help below it and an error that is a sentence, not only a red border.

The label sits `space-2` above the input, in `label`; fields sit `space-6` apart. Typed text is
`input` (16px) on every device, because iOS Safari zooms into anything smaller. Help text is where an
accounting term gets its one-line explanation. An error says what is wrong and what to do; it puts
`danger` on the border and the sentence below, and is announced with the field.

Ask for the right keyboard: `inputMode="decimal"` for an amount, `type="email"` for an email, and
`autoComplete` so the browser can fill names and emails.

Props: `label` (required), `help`, `error`, and any `<input>` attribute: `value`, `defaultValue`,
`onChange`, `type`, `inputMode`, `autoComplete`, `name`, `required`.

```html
<x-import component-from-global-scope="CFOKit.TextField" label="Company name" default-value="[COMPANY NAME]"></x-import>
```
