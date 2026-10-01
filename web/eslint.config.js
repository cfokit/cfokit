import js from "@eslint/js";
import reactHooks from "eslint-plugin-react-hooks";
import globals from "globals";
import tseslint from "typescript-eslint";

export default tseslint.config(
  { ignores: ["dist", "dist_keycloak"] },
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
);
