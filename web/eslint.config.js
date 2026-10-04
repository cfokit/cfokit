import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "dist_keycloak", "dist-design-system", "public/keycloakify-dev-resources"] },
  js.configs.recommended,
  tseslint.configs.strict,
  reactHooks.configs.flat["recommended-latest"],
  {
    languageOptions: { globals: globals.browser },
    rules: {
      // Text from a user's file or from the books is rendered as text, never as markup
      // (ADR-0049 § 6).
      "no-restricted-syntax": [
        "error",
        {
          selector: "JSXAttribute[name.name='dangerouslySetInnerHTML']",
          message: "Render external text as text (ADR-0049 § 6).",
        },
      ],
    },
  },
  // The design system's producer runs in Node, and its previews in the design system's frame.
  {
    files: ["design/publish/*.mjs"],
    languageOptions: { globals: globals.node },
  },
);
