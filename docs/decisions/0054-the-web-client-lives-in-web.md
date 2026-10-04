---
status: "proposed"
kind: "substrate"
date: 2026-10-01
decision-makers: [Geoff]
---

# ADR-0054: The web client lives in a top-level `web/` directory, with its toolchain

## Context and Problem Statement

[ADR-0049](0049-cfokit-has-a-web-client.md) gives CFOKit a web client: a React single-page
application in TypeScript, built by Vite into static files that the REST service serves, with
pnpm, ESLint, Vitest and Playwright as its tooling. It also gives the bundled issuer a sign-in
theme written with Keycloakify from the client's own components, a `tokens.json` exported from
Claude Design that generates the client's Tailwind theme, and — through
[ADR-0058](0058-getting-started-is-one-path-on-the-web.md) — the
getting-started pages, with their export reader in TypeScript.

None of these has a place in the repository. [ADR-0020](0020-repository-layout-artifact-kinds.md)
organizes directories by artifact kind, and its directories hold Python source (`src/`), skill
bundles (`skills/`), deployment configuration (`infra/`) and documents (`docs/`). A browser
application is none of those. It has its own language, its own package manager and lockfile, its
own dependency graph shipped to browsers rather than installed on a server, and a build whose
output is files rather than an importable package.

Three facts about the existing layout constrain where it can go:

* `src/cfokit/` is what the build backend packages: `pyproject.toml` names `packages =
  ["src/cfokit"]` for the wheel, and it is a PEP 420 namespace, so any directory placed there
  becomes part of the distribution and a candidate namespace package.
* `infra/` supplies environment and issuer configuration and is not coupled to the application
  (`CLAUDE.md`, repository map). ADR-0049 § 1 places the sign-in theme "beside its realm in
  `infra/keycloak/`", but the theme is built from the client's components, so putting its source
  there couples `infra/` to application code.
* The client's types are generated from `docs/contracts/openapi.json`, which CI gate 5 holds equal
  to what the server generates (ADR-0015). A change to the API and the client code that follows
  from it have to be reviewable together.

Keycloakify supports both shapes the theme could take: a separate project forked from its starter,
which its documentation recommends, or a Vite plugin inside an existing React and Vite application,
whose entry point renders the theme when the issuer supplies `window.kcContext` and the
application otherwise. `keycloakify build` writes the theme as a JAR to `dist_keycloak/`. The
documentation marks the in-application integration "advanced users only" (verified against
docs.keycloakify.dev, 2026-10-01).

## Decision Drivers

* One directory per artifact kind (ADR-0020), and a browser application is its own kind.
* `src/cfokit/` stays Python only, so the wheel, Ruff, mypy and import-linter see nothing else.
* A Python-only change needs no Node toolchain to lint and test, and a client-only change needs
  no Python environment.
* The client's coupling to the server is the published contract and nothing more (ADR-0049 § 4),
  and the layout should make any other coupling awkward rather than merely forbidden.
* `infra/` stays free of application code.
* An API change and the client change it forces land in one pull request (ADR-0015, ADR-0023).
* Build output is produced by the image build and never committed.
* No directory or workspace is created for a package that does not exist yet (ADR-0020, ADR-0022).

## Considered Options

* A top-level `web/` directory holding the client, its sign-in theme, its tokens and its tests
* A directory under `src/cfokit/`
* The built client committed under the server package, beside what serves it
* A pnpm workspace rooted at the repository, with an application and shared packages
* The client in `web/`, the sign-in theme in `infra/keycloak/`
* A separate repository
* The same directory under another name: `client/`, `frontend/`, `app/` or `ui/`

## Decision Outcome

Chosen option: "A top-level `web/` directory holding the client, its sign-in theme, its tokens and
its tests", because it is the only option that keeps each existing tree to one artifact kind
without separating the client from the contract it is typed against.

> The web client lives in `web/`, with one `package.json` and one pnpm lockfile. Everything that
> runs in a browser or builds what does is there, and the product's Node tooling is nowhere
> else. A skill is not part of that rule: its bundle is its own artifact kind and carries
> whatever code the agent's runtime runs, TypeScript included (ADR-0020). `web/` reads from outside itself only `docs/contracts/openapi.json`, and `docs/design/` when it publishes the design system, and its
> build output reaches the image and the issuer through the image build, never through a commit.

### 1. What lives in `web/`

* **The client's source**, in TypeScript, and its unit, component and end-to-end tests. Playwright
  tests are browser tests of a TypeScript application, so they sit with it rather than in the
  Python `tests/` tree.
* **The sign-in theme**, built by the Keycloakify Vite plugin from inside the client's project, so
  it uses the client's components and Tailwind theme by import rather than by copy. ADR-0049 § 1
  requires that the theme and the client look the same, and one project is how that holds without
  a shared package.
* **`tokens.json`**, the one file from Claude Design that enters the repository (ADR-0049 § 10),
  because it is an input to the client's build and has no other consumer.
* **The onboarding panel** of ADR-0058, built here from the client's components, with its
  TypeScript export reader and the reader's tests against the synthetic export.
* **`web/CLAUDE.md`**, carrying the client's rules — the money rule, the `dangerouslySetInnerHTML`
  ban, the license rule for the bundle — so they load when work happens there, as a capability's
  `CLAUDE.md` does under `src/cfokit/`.

How `web/` is organized inside is the client's own business and is not pinned here, any more than
a module's internal files are.

### 2. What crosses the boundary

* **In: `docs/contracts/openapi.json`, and `docs/design/` for publishing.** The generated API
  client is built from the contract. `pnpm design-system` reads the design system's prose from
  `docs/design/` to publish it beside the components (ADR-0049 § 10); nothing the client serves
  is built from it. `web/` imports nothing from `src/`, `skills/` or `infra/`, and nothing outside
  `web/` imports from it.
* **Out to the image: the static build.** A Node stage of the Dockerfile builds `web/` and copies
  the output into the image, where the REST service serves it at `/app/` (ADR-0049 § 5). The
  Python stages do not need Node, and the final image carries no Node runtime. On GCP the same
  files are copied out of that image into a bucket behind a CDN
  ([ADR-0055](0055-on-gcp-the-web-client-is-served-from-a-cdn.md)); they are never built twice.
* **Out to the issuer: the theme JAR.** The bundled issuer receives the built theme through the
  compose build. `infra/keycloak/` keeps the realm and the configuration that selects the theme by
  name, not its source.
* **Never committed:** `node_modules/`, the static build and the JAR are in `.gitignore`.

### Consequences

* Good, because `uv run task lint` and `uv run task test` are unchanged and need no Node, and
  `web/`'s own checks need no Python.
* Good, because the wheel and the Python linters cannot pick up client code: it is outside the
  tree they read.
* Good, because a contract change and its client consequences are one pull request, and gate 5
  already makes the contract the point they meet.
* Good, because the theme and the client share components by import, so a change of look is made
  once.
* Bad, because the repository has a second toolchain with its own lockfile, Dependabot ecosystem,
  CI job and image stage, which every contributor touching `web/` must install.
* Bad, because the in-application Keycloakify integration is the shape its documentation reserves
  for advanced users, and the client's entry point branches on whether the issuer is rendering it.
* Bad, because the theme's code is part of the client's build and the client's code part of the
  theme's. Each is small, and sharing components is what makes it so.
* Neutral, because `infra/keycloak/` keeps only configuration, which is what `infra/` was already
  for.

### Confirmation

* CI's client job runs from `web/` and fails on a lockfile out of date with `package.json`.
* A test asserts that no `package.json`, `pnpm-lock.yaml` or `node_modules/` exists outside `web/`,
  and no `.ts` or `.tsx` file outside it, except within `skills/`.
* `.gitignore` excludes the static build and `dist_keycloak/`; a test asserts neither is tracked.
* Not gated: that `web/` reads nothing from outside itself except the contract and, to publish,
  `docs/design/`. That is review.

## Pros and Cons of the Options

### A top-level `web/` directory holding the client, its sign-in theme, its tokens and its tests

* Good, because it applies ADR-0020's rule to a new artifact kind rather than bending an existing
  directory.
* Good, because it makes the boundary physical: the Python tree and the Node tree do not overlap.
* Bad, because it adds a top-level directory, and the in-application theme integration is the less
  common Keycloakify shape.

### A directory under `src/cfokit/`

The client is part of the product, as the capabilities are, and the REST service serves it.

* Good, because everything that ships in the image would sit under one source root.
* Bad, because hatchling packages everything under `src/cfokit/` into the wheel, so TypeScript
  source and, after a local install, `node_modules/` would be packaged or have to be excluded by a
  rule someone must remember.
* Bad, because `src/cfokit/` is a PEP 420 namespace: a directory there is a namespace package to
  mypy and import-linter, and they would have to be told to ignore it. ADR-0020 holds that tree to
  installable Python, and it would stop meaning that.

### The built client committed under the server package, beside what serves it

Serving needs no build stage at all if the files are already there.

* Good, because the image build stays Python only.
* Bad, because every client change commits minified build output, which is unreviewable, and the
  committed build and the source can disagree with nothing to catch it.
* Bad, because `server` is the composition point, the only place that knows the module list, and
  a client is not a module (`CLAUDE.md`).

### A pnpm workspace rooted at the repository, with an application and shared packages

The conventional layout for a TypeScript monorepo: `apps/web`, `packages/ui`, `packages/login-theme`,
a root `package.json`. It is also the shape Keycloakify's documentation steers towards, with the
theme as its own project.

* Good, because the theme would be a standard Keycloakify project, and shared components a named
  package.
* Bad, because it puts Node tooling at the repository root, where every contributor meets it,
  including on a Python-only change.
* Bad, because it builds a workspace for packages that do not exist apart from one another. One
  client and one theme share one component set; the second consumer that would justify a shared
  package is not here. A workspace shaped ahead of its members is the mistake ADR-0020 and
  ADR-0022 already record, and a pnpm workspace inside `web/` remains available if one arrives.

### The client in `web/`, the sign-in theme in `infra/keycloak/`

ADR-0049 § 1's original placement: the theme belongs to the issuer, so it sits with the issuer's
realm.

* Good, because everything the bundled issuer loads would be in one directory.
* Bad, because the theme imports the client's components, so `infra/` would hold application code
  that depends on `web/`. `infra/` supplies configuration and is coupled to nothing.
* Bad, because the theme would need its own `package.json` and lockfile, or reach into `web/`'s,
  and either way Node tooling exists in two places.

### A separate repository

Common when a front end has its own team and release cadence.

* Good, because each repository would have one toolchain.
* Bad, because the client's types come from `docs/contracts/openapi.json`, and an API change and
  its client change would become two pull requests in two repositories, against the lockstep
  ADR-0023 chose for the image.
* Bad, because the image build would have to fetch the client at a matching version, which is
  release machinery for one team.

### The same directory under another name

* `client/` is the most literal and the most ambiguous: an OAuth client (ADR-0032), an MCP client,
  and the issuer's public client for this very page are all called clients in this repository.
* `frontend/` implies a backend-for-frontend, which ADR-0049 rejected.
* `app/` is what ADR-0009 calls the one application the server runs.
* `ui/` is accurate but names the presentation rather than the artifact, and an MCP App or a Slack
  message is also a UI.

`web/` names where the artifact runs, which is the property that makes it a different kind.

## More Information

**Follow-on obligations.**

* The repository map in `CLAUDE.md` carries a `web/` row from when the directory exists, with its
  boundary: reads only the published contract, and the design system's prose to publish it; never
  imported from.
* Dependabot gains an npm ecosystem for `/web`, on the same monthly schedule and cooldown as the
  others.
* `.dockerignore` excludes `web/node_modules/` and build output from the build context.

**Reversal cost.** Low while `web/` is small: moving it is a rename plus the Dockerfile stage, the
CI job and the Dependabot entry. Splitting it into a workspace later is an internal change to
`web/` that touches nothing outside it.

Related: [ADR-0020](0020-repository-layout-artifact-kinds.md) (the layout this extends),
[ADR-0049](0049-cfokit-has-a-web-client.md) (the client),
[ADR-0058](0058-getting-started-is-one-path-on-the-web.md) (the
getting-started pages and their export reader),
[ADR-0023](0023-one-image-many-entrypoints.md) (one image), and the Keycloakify Vite integration at
docs.keycloakify.dev.

## Revisit when

* A second TypeScript artifact needs the client's components — an MCP App, an embeddable widget,
  the invoice page if it is built as a client page — which is the trigger for a workspace inside
  `web/`.
* The in-application Keycloakify integration breaks on a Keycloakify or Keycloak upgrade, which
  reopens the theme as a separate project inside `web/`.
* The client acquires a team or a release cadence of its own, which reopens a separate repository.
