---
status: "proposed"
kind: "requirement-driven"
date: 2026-09-29
decision-makers: [Geoff]
---

# ADR-0048: CFOKit has a web client, served by the API and signed in through the issuer

**Requirements served:** `PLT-24`, `IAM-10`, `NFR-19`.

## Context and Problem Statement

The agent keeps and questions the books, and most of what an operator does happens in a
conversation. Some work goes badly there. Landing a company's history is the first case: a
deterministic bulk transfer that a model adds nothing to and pays heavily for
([ADR-0049](0049-books-are-imported-through-the-web-client.md)). There will be others, and an
operator — self-hosting or on a hosted service — needs a place to do them signed in as
themselves (`PLT-24`).

[ADR-0012](0012-binding-non-goals-and-scope-discipline.md) gates a web UI because it is a second
product surface with "its own auth, session handling, XSS surface, and design work". This record
is that gate being passed deliberately, and it has to answer each of the four rather than wave
them through.

`IAM-10` constrains the answer before anything else: identity is delegated, and CFOKit never
issues credentials, stores passwords, or operates a login flow.

## Decision Drivers

* `IAM-10`: no password, no credential issued, no login form of CFOKit's own.
* One authorisation path. The web client may do nothing an agent holding the same person's grants
  could not, or permissions exist in two places and diverge.
* One image and one deployable (ADR-0023); portable to any target and to a laptop (ADR-0004).
* No stateful sessions against a scale-to-zero service (ADR-0017).
* A small, reviewable security surface in the browser.
* Nothing copyleft shipped to the operator's machine (`CLAUDE.md`, Licensing).
* Layout and visual design are made in design tooling, and a record must not pin them.

## Considered Options

* Static pages served by the REST service, signing in with PKCE as a public client, token held in memory
* A separately deployed single-page application
* A backend-for-frontend holding the session in a server-side cookie
* Server-rendered pages from a template engine

## Decision Outcome

Chosen option: "Static pages served by the REST service, signing in with PKCE as a public client,
token held in memory", because it is the only option that adds no session state, no second
deployable and no second authorisation path.

> The web client is static HTML, CSS and JavaScript served by the REST service under its own
> `PUBLIC_BASE_URL`. It signs the person in through the issuer with the authorization code flow
> and PKCE, holds the token in page memory only, and calls the same REST API an agent calls. It
> has no endpoints of its own.

### 1. Auth is the issuer's

The page redirects to the issuer, the issuer renders its own login, and the page receives a code
it exchanges for a token as a public client — no secret, because a browser cannot keep one. CFOKit
still issues nothing and shows no login form (`IAM-10`). The token is the person's own, carrying
no `act` claim, so acts reserved to a person (ADR-0042) are available to them here exactly as the
API already decides.

### 2. There is no session

The token lives in page memory and is never written to storage or a cookie. Closing the tab signs
the person out. The server holds nothing between requests, which is what a scale-to-zero service
needs and what makes CSRF inapplicable: nothing is sent that a browser attaches on its own.

The cost is signing in on every visit. Staying signed in means a refresh token in the browser or a
server-held session, and that is decided when a page is used often enough for it to matter.

### 3. No endpoints of its own

The web client is a client of the published REST API, with the person's bearer token, like any
other. Every permission check is the one the API already makes. A capability the web client needs
and the API lacks is a change to the API, reviewed as a contract change (ADR-0015).

### 4. Same origin, one image

Served by the REST service, the pages and the API share an origin, so there is no CORS policy to
get wrong, and the web client ships in the one image to wherever that image runs.

### 5. A small browser surface

`Content-Security-Policy: default-src 'self'`, and no script, style or font from another origin.
Plain ES modules with no framework and no build step, until a page's complexity says otherwise.
Anything read from a user's file or from the books is rendered as text, never as markup. Whatever
ships to the browser carries no copyleft licence.

### 6. Layout is not decided here

What the pages look like is designed in Claude Design and implemented against the behaviour each
page's record states. A record names the states a page must handle; it does not draw them.

### Consequences

* Good, because the operator gets a surface for work that goes badly in a conversation, on any
  deployment, with nothing installed.
* Good, because there is no password, no session store and no second permission model to secure.
* Good, because it ships and deploys with everything else.
* Bad, because signing in on every visit will be friction once pages are used daily.
* Bad, because the product now has a browser attack surface, and the CSP is its main defence.
* Bad, because every capability the web client grows is API surface first, which is slower than a
  page talking to its own endpoint — deliberately.
* Neutral, because ADR-0012 keeps an admin console gated; this passes the gate for a web client only.

### Confirmation

* A test asserts every web-client response carries the CSP header, and that no page references
  another origin.
* A test asserts the REST service serves no route under the web client's path that is not a
  static file — the "no endpoints of its own" rule, observed at the surface.
* The public client in `infra/keycloak/cfokit-realm.json` permits only the authorization code
  flow with PKCE (S256).
* Not gated: that page code renders external text as text. That is review, backed by the CSP.

## Pros and Cons of the Options

### Static pages served by the REST service, signing in with PKCE as a public client, token held in memory

* Good, because it meets every driver.
* Bad, because a token held by page script is readable by any script running in that page, which
  is why the CSP and the no-third-party rule carry weight.

### A separately deployed single-page application

The conventional shape for a modern web client.

* Good, because the client releases independently of the server.
* Bad, because it is a second deployable with its own hosting on every target, including a laptop,
  against ADR-0023 and ADR-0004.
* Bad, because a second origin means CORS, and a misconfigured CORS policy is an authorisation bug.

### A backend-for-frontend holding the session in a server-side cookie

The strongest security posture for tokens: they never reach page script, only an `HttpOnly` cookie
does.

* Good, because script injected into a page cannot read a token.
* Bad, because the server holds a session per person, which a scale-to-zero service loses on every
  cold start or has to store somewhere, and ADR-0012 excludes a caching layer.
* Bad, because a cookie the browser attaches on its own brings CSRF back.
* Bad, because CFOKit would be running the code exchange and holding the session — the nearest
  thing to operating a login flow short of rendering one, which `IAM-10` is written against.

### Server-rendered pages from a template engine

* Good, because it is simple and needs little JavaScript.
* Bad, because a template engine is a runtime dependency, and runtime dependencies are decisions.
* Bad, because the first page reads a file in the browser anyway, so the script cannot be avoided.

## More Information

**Follow-on obligations.**

* A public client for the web client in `infra/keycloak/cfokit-realm.json`: authorization code with
  PKCE, redirect URIs under the REST service's `PUBLIC_BASE_URL`. A deployment sets its own.
* ADR-0012's table notes that the web UI gate is passed by this record, and the admin console's is
  not.
* A root `CLAUDE.md` rule, derived from § 3 and § 5: the web client has no endpoints of its own,
  and loads nothing from another origin.

**Reversal cost.** Low while the web client is one page; rising with every page added.

Related: ADR-0012 (the gate), ADR-0019 (the issuer), ADR-0023 (one image), ADR-0042 (acts reserved
to a person), ADR-0049 (the first page).

## Revisit when

* A page is used often enough that signing in per visit is the complaint — the trigger for choosing
  between a browser-held refresh token and a server-held session.
* A page's script outgrows plain modules, which is the trigger for a build step.
* A host renders MCP Apps well enough that pages could live inside the conversation instead.
