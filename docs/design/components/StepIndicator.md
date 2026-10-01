# StepIndicator

Where the person is in a sequence of steps, such as onboarding.

From `bp-tablet` it lists every step: done ones in `ink-muted` with a check, the current one in
`accent`, later ones numbered in `ink-muted`. On a phone it is one line: "Step 2 of 4: Import your
books". On desktop it sits in a column beside the content.

Props: `steps` (names, in order, sentence case), `current` (the index of the current step; those
before it are done), `label` ("Setup steps").

```html
<x-import component-from-global-scope="CFOKit.StepIndicator" steps="{{steps}}" current="{{1}}" label="Setup steps"></x-import>
```
