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
corepack pnpm theme                       # regenerate design/theme*.css from design/tokens.json
corepack pnpm design-system               # build the Design System artifact's files, then
                                          # mount every preview on React 18, as the canvas does
```

`pnpm dev` also serves the component gallery at `/app/gallery.html`: every component in its
states, for checking a change at phone, tablet and desktop widths. It is not part of the build.

Run `lint`, `test` and `build` before reporting work complete, as the `web client` CI job does.

## Rules

- **Money never becomes a JavaScript `number`.** Amounts arrive as decimal strings and are
  displayed as strings or through `big.js`. Never sum figures in the client; display the totals
  the API computed. (ADR-0005, ADR-0049 § 9)
- **External text is rendered as text.** `dangerouslySetInnerHTML` is forbidden, and lint fails
  on it. (ADR-0049 § 6)
- **Nothing from another origin.** No script, style, font or image from a CDN or any third
  party; everything is bundled. The CSP is `default-src 'self'`. (ADR-0049 § 6)
- **A file the build serves is named by its content hash** unless its name must stay fixed, as
  `index.html`'s and the license texts' do. A hashed file is cached for a year by a browser or
  any CDN and needs no purge on deploy; a fixed name is revalidated on every request. Import
  fonts, images and icons by path from `design/` or `src/`; `public/` holds only fixed names. (ADR-0055 § 2)
- **Nothing about the books or the session in browser storage.** Tokens live in page memory. The
  one exception is the PKCE verifier and `state`, in `sessionStorage` for the sign-in round trip
  only. The service worker caches the static build, never an API response. (ADR-0049 § 2, § 8)
- **Where the operator is lives in the URL or on the server**, never in client state that a
  reload loses. (ADR-0049 § 2)
- **The repository is the design system's source, split by kind** (ADR-0049 § 10). Prose — the
  brand book, the marks' notes, each component's guide — is in `docs/design/`. What the client
  builds from — `tokens.json`, the fonts, the marks, the theme generator and the publishing
  build — is in `design/`. The components are in `src/components/`. The Design System artifact in
  Claude Design is published from these by `pnpm design-system` and never edited in its page.
- **The look comes from `design/tokens.json`, and nowhere else.** `design/theme.css` and
  `design/theme.design-system.css` are generated from it, and a test fails when they disagree:
  change the tokens, run `pnpm theme`. The theme clears Tailwind's defaults, so a color, size or
  breakpoint outside the system has no utility; do not add one in CSS or with an arbitrary
  value.
- **Pages are built from `src/components/`**, the components `docs/design/README.md`
  describes; a page that needs one that is missing adds it there, with a test, a place in the
  gallery, a guide in `docs/design/components/` and a preview in `design/publish/previews/`;
  `pnpm design-system` fails until both exist. A `text-*` style sets size, line height and weight but not the family: `display` and
  `heading` styles also take `font-display`.
- **Amounts are shown through `Money` or `MoneyTable`**, which round half-up to the display scale
  once and show negatives in parentheses (ADR-0025, RPT-12). Never format an amount by hand.
- **No copyleft in what ships to the browser.** Check the license before adding a runtime
  dependency; fonts under OFL-1.1 ship with their license texts in the same build. (ADR-0049 § 9)
- **Adding a dependency is a decision**, made against the stack in ADR-0049 § 9. pnpm refuses
  any release younger than a week (`pnpm-workspace.yaml`); do not add exclusions to get around
  it.
