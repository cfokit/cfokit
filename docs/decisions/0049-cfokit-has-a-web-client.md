---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-29
decision-makers: [Geoff]
---

# ADR-0049: CFOKit has a web client, served by the API and signed in through the issuer

**Requirements served:** `PLT-24`, `IAM-06`, `IAM-10`, `IAM-22`, `IAM-23`, `IAM-24`, `IAM-25`,
`IAM-26`, `NFR-19`.

## Context and Problem Statement

The agent keeps and questions the books, and most of what an operator does happens in a
conversation. Some work goes badly there, and onboarding is the clearest case. Creating an
account, creating the company, and landing its history from the system it already runs are
deterministic steps with one right answer each. A model adds nothing to them, and the last one it
pays heavily for ([ADR-0041](0041-import-is-parsed-where-the-file-is.md) § 6). An operator
needs a place to do them signed in as themselves (`PLT-24`), before a conversation has anything
to talk about.

CFOKit is built to run securely as a hosted, multi-tenant service and, from the same image, on one
person's own hardware (ADR-0004, ADR-0023). The web client has to be correct for the first
without costing the second anything. It runs in whatever current browser the operator has, so
the browsers' differences in storage, cookies and state are part of the design rather than
something to meet later.

[ADR-0012](0012-binding-non-goals-and-scope-discipline.md) gates a web UI because it is a second
product surface with "its own auth, session handling, XSS surface, and design work". This record
is that gate being passed deliberately, and it has to answer each of the four rather than wave
them through.

Signing in is what any commercial web product offers: an account with a password, reset without
an administrator, a second factor, passkeys, and Google and Microsoft accounts (`IAM-22` to
`IAM-26`). `IAM-10` bounds how: a person signs in themselves, in a browser, and credentials never
pass through an agent, a model or CFOKit's own API. Authentication is delegated to the identity
provider rather than written here.

## Decision Drivers

* Credentials reach the identity provider and nothing else — no agent, no model, not CFOKit's API
  (`IAM-10`).
* Sign-in and sign-up look and behave like the rest of the product.
* One authorization path. The web client may do nothing an agent holding the same person's grants
  could not, or permissions exist in two places and diverge.
* One image and one deployable (ADR-0023); portable to any target and to a laptop (ADR-0004).
* No stateful sessions against a scale-to-zero service (ADR-0017).
* A small, reviewable security surface in the browser.
* Correct in every current major browser, whatever each does to storage and cookies.
* Onboarding with no model in it: account, entity and import are each deterministic.
* Nothing copyleft shipped to the operator's machine (`CLAUDE.md`, Licensing).
* Layout and visual design are made in design tooling, and a record must not pin them.

## Considered Options

* A single-page application built to static files, served by the REST service, signing in with PKCE
* A separately deployed single-page application
* An offline-first client that keeps the books on the device and queues writes
* Static pages with no framework and no build step
* A backend-for-frontend holding the session in a server-side cookie
* Server-rendered pages from a template engine

## Decision Outcome

Chosen option: "A single-page application built to static files, served by the REST service,
signing in with PKCE", because it is the only option that adds no session state, no second
deployable and no second authorization path.

> The web client is a React single-page application in TypeScript, built to static files and
> served at `/app/` on the REST API's origin, under its `PUBLIC_BASE_URL`. It signs the person in through the
> issuer with the authorization code flow and PKCE, keeps its tokens in page memory, keeps what it
> knows about progress on the server, and calls the same REST API an agent calls. It has no
> endpoints of its own. Its first job is onboarding, end to end: create an account, create the
> entity, import its books. It is a progressive web app: one set of pages for desktop, tablet and
> phone, installable to a home screen, keeping nothing about the books on the device.

### 1. Sign-in is the issuer's, and looks like CFOKit

The page redirects to the issuer and receives a code it exchanges for a token as a public client
— no secret, because a browser cannot keep one. The token is the person's own, carrying no `act`
claim, so acts reserved to a person (ADR-0042) are available to them here exactly as the API
already decides.

The screens on the way — sign-in, sign-up, password reset, second factor, passkey — are the
issuer's pages rendered through a login theme built from the web client's own React components
and Tailwind theme, with Keycloakify (MIT). They are CFOKit's screens to the person using them;
the password, the second factor and the passkey go to the issuer and nowhere else (`IAM-10`).

Password, second-factor, passkey and Google and Microsoft sign-in are the issuer's features,
enabled in its configuration, not application code. The theme is built with the web client, from
its source in `web/` ([ADR-0054](0054-the-web-client-lives-in-web.md)), and loaded by the bundled
issuer, whose realm in `infra/keycloak/` selects it; a deployment that uses another issuer brands
that one, and the application is unchanged (ADR-0019).

### 2. State lives on the server; the browser keeps almost nothing

Browsers disagree most about storage and cookies — Safari's Intelligent Tracking Prevention caps
and clears script-written storage and blocks third-party cookies, Firefox partitions storage per
site, private windows discard it — so the design keeps nothing there that matters.

* **Tokens live in page memory**, the access token and the refresh token both, and are never
  written to storage or a cookie of ours. The refresh token keeps a long import going past the
  access token's lifetime, whatever lifetime a deployment's issuer sets.
* **The one exception is the sign-in round trip.** The PKCE verifier and `state` have to survive
  the page navigating to the issuer and back, so they sit in `sessionStorage` for that trip and are
  deleted on return. `sessionStorage` is per tab and cleared with it, in every major browser.
* **Where the operator is in onboarding is read from the API on every load**: is there an entity
  they own, and has it been imported. A reload, a second tab, another browser or another device
  arrives at the right step, because the answer was never kept in the browser that asked.
* **A reload signs back in without a password.** The issuer's own session cookie is first-party
  to the issuer and is sent on the top-level redirect, which every browser allows. What is *not*
  used is renewal in a hidden iframe (`prompt=none`): Safari and Firefox block the issuer's cookie
  in a third-party frame, so it fails in exactly the browsers least likely to be tested.
* **Tabs are independent**, each signed in on its own.
* **Nothing the browser attaches by itself carries authority**, so there is no CSRF to defend
  against, and the server holds no session a scale-to-zero instance would lose.

Staying signed in across a closed browser is not offered. It needs a refresh token in persistent
storage or a server-held session, and that is decided when a page is used daily.

### 3. Onboarding is three steps, and each is someone else's act

**Superseded by [ADR-0058](0058-getting-started-is-one-path-on-the-web.md).** The other sections stand.

* **Create an account** is the issuer's registration page in CFOKit's theme (§ 1), reached from the
  sign-in redirect, or a Google or Microsoft account (`IAM-22`, `IAM-25`, `IAM-26`). Whether a
  deployment allows open registration, and what it verifies, is that deployment's configuration.
  The bundled issuer allows it. Where a deployment has no mail relay, the address is not
  verified and a forgotten password is reset by the operator
  ([ADR-0052](0052-notifications-are-records-delivered-after-commit.md)).
* **Create the entity** is the existing `create_entity` operation, which needs an authenticated
  identity and no prior role and makes the caller the owner (`IAM-05`, `IAM-06`).
* **Import its books** is ADR-0051.

No model is involved. The conversation starts once there are books to talk about.

### 4. No endpoints of its own

The web client is a client of the published REST API, with the person's bearer token, like any
other. Every permission check is the one the API already makes. A capability the web client needs
and the API lacks is a change to the API, reviewed as a contract change (ADR-0015).

### 5. Same origin, one image

The pages live at `/app/` on the API's origin, so there is no CORS policy to get wrong, and the
web client ships in the one image to wherever that image runs. The REST service serves `/app/`
from the build inside the image, and redirects `/` to it. A target may serve the same files from
a CDN at the same path and origin instead; on GCP it does
([ADR-0055](0055-on-gcp-the-web-client-is-served-from-a-cdn.md)).

### 6. A small browser surface

`Content-Security-Policy: default-src 'self'`, and no script, style or font from another origin:
everything the client needs is built into its own bundle, as files, never inlined as `data:`
URIs. The one other origin the page may reach is the issuer's, with `connect-src`: signing in
fetches its metadata and exchanges a code at its token endpoint (§ 1). Anything read from a user's file or
from the books is rendered as text, never as markup — which React does by default, and
`dangerouslySetInnerHTML` is forbidden by lint. Whatever code ships to the browser carries no
copyleft license.

### 7. Every page works on desktop, tablet and phone, in current browsers

The current and previous major versions of Chrome, Edge, Firefox and Safari on desktop; Safari on
iOS and iPadOS, which is also the engine of every other browser there; and Chrome on Android.
Every browser API the web client depends on is Baseline — supported by all of them — and none is
experimental: `fetch`, the File API, `DecompressionStream` with `deflate-raw`, `DOMParser`, Web
Workers, service workers, `sessionStorage`, and `crypto.subtle.digest` for the PKCE challenge.
The last two require a secure context, which HTTPS gives on a deployment and `http://localhost`
gives on one machine.

Every page is designed at phone, tablet and desktop widths, and the layout follows the design
system's breakpoints. Nothing depends on hover or on dragging: choosing a file is a button that
opens the device's picker, and dropping one on a desktop is a shortcut beside it.

### 8. Installable, and nothing about the books is kept on the device

The web client is a progressive web app, so an operator can install it to a home screen or a
desktop and open it like an application.

* **A web app manifest**, served with the pages: the name, the icons from the design system,
  standalone display, and a theme color matching the page ground in each theme.
* **A service worker that caches the application, never the books.** It serves the static build —
  HTML, script, styles, fonts, icons — versioned per build, and its scope is the web client's path,
  so API routes are outside it. No API response, no figure, and no token is ever cached or written
  to device storage (§ 2).
* **Offline, it says so and changes nothing.** The installed app opens and shows that it is
  offline. No write is attempted or queued for later: a change to the books needs the server,
  where the idempotency keys, the lock and the audit record are.
* **An update is offered, never forced.** A new build waits until the operator chooses "Reload to
  update", because a reload interrupts whatever the operator is in the middle of.

### 9. The stack

A single-page application in TypeScript, built by Vite into static files the REST service serves.
The build is a stage of the one image; nothing is served from a Node process.

| Concern | Choice | Why this one |
|---|---|---|
| Language | TypeScript, strict | The API's types reach the page; a changed contract fails the build |
| Build | Vite | Static output, so same-origin serving and the one image survive |
| Framework | React | The largest ecosystem for data-heavy UI; every library below is first-class on it |
| Routing | TanStack Router | Type-checked route parameters. Where the operator is — entity, step — lives in the URL, so it survives a reload and can be linked |
| Server state | TanStack Query | Almost all state is the server's. Caching, retry and loading states without the client holding figures of its own |
| API client | `openapi-typescript` + `openapi-fetch`, generated from `docs/contracts/openapi.json` | The contract gate 5 already guards becomes the client's types |
| Client state | Component state and context; Zustand only if something is genuinely global | There is little that is not server state or the URL |
| Components | Radix primitives | Accessible behavior — focus, keyboard, ARIA — with no imposed look |
| Styling | Tailwind, its theme generated from the design system's `tokens.json` | One source for color, type and spacing, shared with the designs (§ 10) |
| Tables | TanStack Table | Ledgers, trial balances and reconciliations: sorting, virtualized long lists |
| Forms | React Hook Form + Zod | Validation declared once; schemas can come from the contract |
| Sign-in screens | Keycloakify | The issuer's pages written as React components on the client's theme (§ 1) |
| Auth | `oidc-client-ts` + `react-oidc-context` | Maintained PKCE, refresh and redirect handling. Configured with an in-memory user store; only its sign-in state uses `sessionStorage`, as § 2 requires |
| Money | `big.js` | Amounts arrive as decimal strings and are displayed without ever becoming a JavaScript `number` |
| Parsing | A Web Worker, called through Comlink | A large export does not block the onboarding panel's page (ADR-0058) |
| Tests | Vitest, Testing Library, MSW; Playwright end to end; axe for accessibility | Component, contract-mocked and cross-browser layers |
| Fonts | Public Sans (interface and money) and Archivo Narrow (display), bundled from their upstream releases | The design system's faces, served from the client's own origin, content-hashed like the rest of the build, with their license texts in the same build; the system interface font is every stack's fallback |
| Tooling | pnpm with a pinned lockfile; ESLint with typescript-eslint; Prettier | Pinned and updated by Dependabot, like every other dependency |

Licenses, checked against each project's repository: all code that ships to the browser is MIT
or Apache-2.0. The two fonts are under the SIL Open Font License 1.1, the license open-source
fonts are published under: free to bundle and redistribute with any software, on the condition
that the license text travels with the font files. axe-core is MPL-2.0 and is test tooling only;
it must never enter the bundle.

**Money gets the rule the server already has.** A float never touches an amount (ADR-0005): the
client never converts one to `number`, never sums one, and displays totals the API computed. A
lint rule enforces it, the front-end counterpart of `check-money`.

**Within the stack, the alternatives lost on specific grounds.** Svelte and Vue are smaller and
pleasant, and have thinner ecosystems for tables, accessible primitives and OIDC; Angular brings a
whole framework's conventions to a team this size. CSS Modules would work, but a design token
maps onto a Tailwind theme directly and onto CSS Modules only by convention. React Aria is the
stronger accessibility library; Radix has the larger ecosystem of styled components built on it.
Redux solves a client-state problem this application does not have.

### 10. Layout is designed in Claude Design, against a design system the repository holds

What the pages look like is designed in Claude Design and implemented against the behavior each
page's record states. A record names the states a page must handle; it does not draw them.

Claude Design's artboards are HTML with inline styles and are a reference, not source: nothing is
copied from them into the client. What the two share is the CFOKit design system, and the
repository is its source, split by kind:

* **Prose in `docs/design/`**: the brand book, the notes on the marks, and a guide per component.
* **Everything the client builds from in `web/design/`**: `tokens.json` — color, type, spacing,
  radii — from which the client's Tailwind theme is generated, the font files and the marks.
* **The components in `web/src/components/`.**

`pnpm design-system` builds a Design System artifact's files from those three places: the brand
book, the tokens, fonts and marks, and the components as a bundle with a guide and a live preview
each. That artifact is what Claude Design installs on a canvas, so artboards use the components
the client ships. It is a published copy, changed by changing the repository and publishing again;
an edit made in its page is overwritten by the next publish. A change of look is a change of
tokens, made once, in a pull request.

### Consequences

* Good, because onboarding is deterministic from account to imported books, on any deployment.
* Good, because one code base serves desktop, tablet and phone, installed or in a tab.
* Good, because a reload, a new tab or another device resumes where the server says the operator
  is, in any of the four browsers.
* Good, because there is no password, no session store and no second permission model to secure.
* Good, because it ships and deploys with everything else.
* Bad, because signing in on every visit will be friction once pages are used daily.
* Bad, because a reload mid-import means choosing the file again; the parsed books are not kept.
* Bad, because the installed app does nothing useful offline except say so.
* Bad, because three browser engines in CI add minutes to every run, and Playwright's WebKit is a
  close proxy for Safari rather than Safari itself.
* Bad, because the repository gains a Node toolchain, an npm dependency tree shipped to browsers,
  and a build stage in the image — a second supply chain to pin, update and audit.
* Bad, because the product now has a browser attack surface, and the CSP is its main defense.
* Bad, because every capability the web client grows is API surface first, which is slower than a
  page talking to its own endpoint — deliberately.
* Neutral, because ADR-0012 keeps an admin console gated; this passes the gate for a web client only.

### Confirmation

* An end-to-end onboarding test runs in CI in Chromium, Firefox and WebKit through Playwright
  (Apache-2.0, CI-only tooling): register, create the entity, import the synthetic export, reload
  mid-import and finish, and check the recorded reconciliation. It also asserts that nothing but
  the sign-in round trip is left in browser storage. It runs at desktop width and, with touch
  emulation, at phone and tablet widths — emulation, not a real iPhone or Android device.
* A test asserts the service worker's cache holds only files of the static build, and that
  offline the installed app shows the offline notice and sends no request that changes the books.
* A test asserts every web-client response carries the CSP header, and that no page references
  another origin.
* A test asserts the REST service serves no route under the web client's path that is not a
  static file — the "no endpoints of its own" rule, observed at the surface.
* The public client in `infra/keycloak/cfokit-realm.json` permits only the authorization code
  flow with PKCE (S256).
* CI fails when a copyleft license appears in the production bundle, the web client's or the
  sign-in theme's. Font files under OFL-1.1 are the one allowance, and only with their license
  texts in the same build.
* A lint rule forbids converting an amount to a JavaScript `number` and forbids
  `dangerouslySetInnerHTML`.
* Not gated: that page code renders external text as text. That is review, backed by the CSP.

## Pros and Cons of the Options

### A single-page application built to static files, served by the REST service, signing in with PKCE

* Good, because it meets every driver.
* Bad, because a token held by page script is readable by any script running in that page, which
  is why the CSP and the no-third-party rule carry weight.

### A separately deployed single-page application

The conventional shape for a modern web client.

* Good, because the client releases independently of the server.
* Bad, because it is a second deployable with its own hosting on every target, including a laptop,
  against ADR-0023 and ADR-0004.
* Bad, because a second origin means CORS, and a misconfigured CORS policy is an authorization bug.

### Static pages with no framework and no build step

The smallest thing that serves one import page: plain modules, no toolchain, nothing to update.

* Good, because there is no npm supply chain and no build stage.
* Bad, because the client is meant to grow past onboarding, and a hand-rolled stack is outgrown
  and rewritten at the point it holds the most pages. Routing, server-state caching, accessible
  components, forms and OIDC would each be written here instead of maintained elsewhere.

### An offline-first client that keeps the books on the device and queues writes

The strongest case for an installed app: read the books and record a receipt on a plane, and
reconcile when the connection returns.

* Good, because the app would be useful with no connection.
* Bad, because a company's books would sit in device storage, which Safari clears on its own
  schedule and which outlives the person's sign-in — financial data at rest on every phone that
  ever opened it.
* Bad, because a queued write reaches a ledger that may have closed the period, reversed the
  entry or changed the rule since, and resolving that on reconnection is a sync engine this
  product does not need yet.

### A backend-for-frontend holding the session in a server-side cookie

The strongest security posture for tokens: they never reach page script, only an `HttpOnly` cookie
does.

* Good, because script injected into a page cannot read a token.
* Bad, because the server holds a session per person, which a scale-to-zero service loses on every
  cold start or has to store somewhere, and ADR-0012 excludes a caching layer.
* Bad, because a cookie the browser attaches on its own brings CSRF back.

### Server-rendered pages from a template engine

* Good, because it is simple and needs little JavaScript.
* Bad, because a template engine is a runtime dependency, and runtime dependencies are decisions.
* Bad, because the first page reads a file in the browser anyway, so the script cannot be avoided.

## More Information

**Reversal cost.** Low while the web client is one page; rising with every page added.

Related: ADR-0012 (the gate), ADR-0019 (the issuer), ADR-0023 (one image), ADR-0042 (acts reserved
to a person), ADR-0058 (onboarding, which this client does not carry for an organization's own
agent).

## Revisit when

* A page is used often enough that signing in per visit is the complaint — the trigger for choosing
  between a persistently stored refresh token and a server-held session.
* A browser changes storage or cookie behavior in a way the CI engines do not show, found by a
  customer rather than a test.
* React Server Components or a server-rendered framework become necessary for something this
  client needs, which would reopen the static, same-origin shape.
* Managed bookkeeping is built. This client, with mobile and tablet apps, becomes the container
  in which CFOKit chooses the model for each part of the experience (ADR-0058), and the context
  this record argues from — onboarding — is rewritten for that offering.
* Operators ask to record or review the books without a connection, which reopens offline-first.
