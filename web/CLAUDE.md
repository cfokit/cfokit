# The web client — working rules

Loaded when you work in `web/`. The client is a React single-page application in TypeScript,
built by Vite into static files and served at `/app/` on the API's origin (ADR-0049, ADR-0054,
ADR-0055). The root `CLAUDE.md` still applies.

## Boundary

- **`web/` reads one file from outside itself: `docs/contracts/openapi.json`.** It imports
  nothing from `src/`, `skills/` or `infra/`, and nothing imports from it. (ADR-0054)
- **No endpoints of its own.** The client calls the published REST API with the person's bearer
  token, like any other client. A capability the API lacks is an API change, reviewed as a
  contract change. (ADR-0049 § 4)
- **The product's Node tooling lives here and nowhere else.** No `package.json`, lockfile or
  TypeScript outside `web/`, except inside a skill's bundle, which carries whatever its runtime
  runs; `tests/test_repository_layout.py` fails if one appears anywhere else.
- **Build output is never committed.** `dist/` and `dist_keycloak/` come from the image build.

## Commands

Run from `web/`, on the Node version `.nvmrc` pins (`nvm use`). pnpm is the version
`package.json` pins in `packageManager`, run through corepack.

```
corepack pnpm install --frozen-lockfile   # install exactly what the lockfile says
corepack pnpm dev                         # Vite dev server with live reload
corepack pnpm lint                        # eslint + prettier --check
corepack pnpm test                        # vitest
corepack pnpm build                       # tsc, then the static build into dist/
corepack pnpm theme                       # regenerate src/design/theme.css from tokens.json
```

Run `lint`, `test` and `build` before reporting work complete, as the `web client` CI job does.

## Rules

- **Money never becomes a JavaScript `number`.** Amounts arrive as decimal strings and are
  displayed as strings or through `big.js`. Never sum figures in the client; display the totals
  the API computed. (ADR-0005, ADR-0049 § 9)
- **External text is rendered as text.** `dangerouslySetInnerHTML` is forbidden, and lint fails
  on it. (ADR-0049 § 6)
- **Nothing from another origin.** No script, style, font or image from a CDN or any third
  party; everything is bundled. The CSP is `default-src 'self'`. (ADR-0049 § 6)
- **Nothing about the books or the session in browser storage.** Tokens live in page memory. The
  one exception is the PKCE verifier and `state`, in `sessionStorage` for the sign-in round trip
  only. The service worker caches the static build, never an API response. (ADR-0049 § 2, § 8)
- **Where the operator is lives in the URL or on the server**, never in client state that a
  reload loses. (ADR-0049 § 2)
- **The look comes from the design system's tokens, and nowhere else.** `src/design/tokens.json`
  is the CFOKit Design System artifact's file, copied verbatim; `theme.css` is generated from it
  and a test fails when they disagree. Change the look in the design system, copy the file, run
  `pnpm theme`. The theme clears Tailwind's defaults, so a color, size or breakpoint outside the
  system has no utility; do not add one in CSS or with an arbitrary value. (ADR-0049 § 10)
- **No copyleft in what ships to the browser.** Check the license before adding a runtime
  dependency; fonts under OFL-1.1 ship with their license texts beside them. (ADR-0049 § 9)
- **Adding a dependency is a decision**, made against the stack in ADR-0049 § 9. pnpm refuses
  any release younger than a week (`pnpm-workspace.yaml`); do not add exclusions to get around
  it.
