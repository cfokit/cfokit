# ActionBar

A screen's actions: pinned to the bottom of the screen on a phone, in thumb reach and above the home indicator; inline after the content from `bp-tablet`.

Put it last on a screen, primary button first. Give the buttons `fullWidth` so they span the bar on a
phone, and `className="tablet:w-auto"` so they size to their words from `bp-tablet`. It keeps the end
of the page clear of the pinned bar by measuring it.

Props: `children`, the buttons.

```html
<x-import component-from-global-scope="CFOKit.ActionBar">
  <x-import component-from-global-scope="CFOKit.Button" variant="primary" full-width="{{yes}}">Import</x-import>
</x-import>
```
