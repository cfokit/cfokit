# AppFrame

The frame every signed-in screen sits in: a header with the mark and the company's name, the person, "Settings" and "Sign out", and the screen's content beneath.

The header is `bar-height` on `surface` with a bottom `rule`. Below `bp-tablet` the person, "Settings" and "Sign
out" move into an "Account" menu. The header and gutters add the device's safe-area insets. Content
is centered and stops widening at `content-max`. Sign-in screens have no frame: the lockup above a
single `Card` on `paper`.

Props: `company`, `person`, `onSignOut`, `onSettings` (optional; shows "Settings" when given), `children` (the screen).

```html
<x-import component-from-global-scope="CFOKit.AppFrame" company="[COMPANY NAME]" person="[PERSON NAME]">
  <h1>Import your books</h1>
</x-import>
```
