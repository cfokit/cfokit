# TextLink

A link that leaves the page: "Forgot your password?", "Create an account", "Back to sign in".

`body` text in `accent`, underlined, `accent-hover` on hover — the `link` button's look. An action
on the page is a `Button`; a `TextLink` goes somewhere else.

Props: `href`, `children`, and any other attribute of an `a`.

```html
<x-import component-from-global-scope="CFOKit.TextLink" href="#">Create an account</x-import>
```
