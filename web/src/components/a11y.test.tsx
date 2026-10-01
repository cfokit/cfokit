import axe from "axe-core";
import { render } from "@testing-library/react";
import { Gallery } from "../gallery/Gallery";

// Every component, as the gallery shows it, passes axe's rules. Color contrast is not among them
// here: jsdom does not lay out or paint. The design system's README sets contrast for every
// token pair, and the tokens are the only colors there are.
test("the components have no accessibility violations axe can find", async () => {
  const { container } = render(<Gallery />);
  const result = await axe.run(container, { rules: { "color-contrast": { enabled: false } } });
  expect(result.violations.map((v) => `${v.id}: ${v.help}`)).toEqual([]);
});
