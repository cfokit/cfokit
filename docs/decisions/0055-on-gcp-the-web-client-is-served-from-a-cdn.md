---
status: "proposed"
kind: "substrate"
date: 2026-10-01
decision-makers: [Geoff]
---

# ADR-0055: On GCP the web client is served from a bucket behind Cloud CDN, on the API's origin

## Context and Problem Statement

The web client is a static build — HTML, script, styles, fonts, icons — produced in the image
build from `web/` ([ADR-0054](0054-the-web-client-lives-in-web.md)) and served at the path
`/app/` on the same origin as the REST API, so that there is no CORS policy, one
`Content-Security-Policy`, and one `PUBLIC_BASE_URL` ([ADR-0049](0049-cfokit-has-a-web-client.md)).
Everywhere, the REST service can serve those files itself, and on a laptop or a self-hosted
machine it does: that is what keeps the whole product to one image and one command (ADR-0004,
ADR-0023).

On GCP the REST service is a Cloud Run service that scales to zero
([ADR-0017](0017-gcp-initial-cloud-target.md)). Serving the client from it has three costs a
hosted product should not carry:

* **The first page load after idle waits for a cold start**, and so does every asset that load
  requests, before the person has done anything.
* **Every asset is a container request**, billed and served from one region, with no edge cache.
* **A deploy removes the previous build's files.** The client splits its script into hashed chunks
  loaded as pages are visited. A tab opened before a deploy asks for chunks the new revision does
  not have, and fails mid-session.

The REST API's routes sit at the root of the origin — `/entities`, `/healthz`, `/readyz` — and
`/.well-known/` must stay there, because protected-resource metadata is discovered at that fixed
location. The client's path is `/app/`.

## Decision Drivers

* The client and the API share one origin, so ADR-0049's reasons for it — no CORS, one CSP, one
  public address — hold on GCP as they do everywhere else.
* No cold start and no container request in the path of a static file.
* An open tab keeps working across a deploy.
* The files served are the files built into the image, so the client and the API in a deployment
  are always one build.
* Declared in OpenTofu, like the rest of the target (ADR-0016), with no second deployment tool.
* Nothing in the application changes per target; the difference lives in `infra/` (ADR-0004).
* Every deployment carries every capability, and a self-hosted one still runs from one image and
  one command.

## Considered Options

* A global external Application Load Balancer: `/app/*` to a Cloud Storage backend bucket with
  Cloud CDN, everything else to Cloud Run
* The REST service serves `/app/` on GCP as it does elsewhere
* The same load balancer with Cloud CDN in front of Cloud Run, and no bucket
* Firebase Hosting, rewriting API paths to Cloud Run
* A bucket and CDN on a separate origin, calling the API cross-origin
* The API moved under `/api/`, the client at the root

## Decision Outcome

Chosen option: "A global external Application Load Balancer: `/app/*` to a Cloud Storage backend
bucket with Cloud CDN, everything else to Cloud Run", because it takes static files off the
scale-to-zero path and keeps the previous build available while keeping one origin and one build.

> On GCP, a global external Application Load Balancer holds the deployment's public address. Its
> URL map sends `/app/` and everything under it to a Cloud Storage backend bucket with Cloud CDN
> enabled, and every other path to the REST service on Cloud Run. The bucket holds the static
> build extracted from the image being deployed.

### 1. One origin, split by path

* `PUBLIC_BASE_URL` is the load balancer's address. The REST service's Cloud Run ingress is
  restricted to internal traffic and Cloud Load Balancing, so it has no second public address for
  a client or a token to be issued against.
* `/app/*` goes to the backend bucket; `/` redirects to `/app/`; every other path, `/.well-known/`
  included, goes to the REST service unchanged.
* A path under `/app/` with no file behind it — a deep link such as `/app/entities/42/import` —
  is answered with `/app/index.html` by the URL map's custom error response policy, matching the
  bucket's 4xx and overriding the status to 200. The client's router takes it from there, as it
  does when the REST service serves the same build.

### 2. The same headers as anywhere else

The backend bucket's custom response headers carry the client's `Content-Security-Policy` and the
other security headers, with the same values the REST service sends for `/app/`. The values have
one source in the repository, which both the service and the OpenTofu read.

Cache lifetimes follow the build, set as each object's `Cache-Control` when it is uploaded:
content-hashed files are immutable for a year; `index.html`, the service worker and the web app
manifest are revalidated on every request, so a deploy reaches an open tab at its next navigation
and the service worker's update prompt (ADR-0049 § 8) fires.

### 3. The bucket holds the image's build, and the previous one

A deploy copies the static build out of the image it is deploying, not from a separate build, so
the bucket and the Cloud Run revision are always the same commit. It uploads the new files before
the new revision takes traffic, and overwrites `index.html` last. Files belonging to the previous
build stay, so a tab opened before the deploy can still load its chunks; files from builds older
than that are removed.

### 4. Everywhere else, nothing changes

The image still contains the static build and the REST service still serves `/app/`. On GCP the
load balancer never routes `/app/` to it, so it is unused there and harmless; on a laptop or a
self-hosted machine it is how the client is served. No code branches on the target.

### Consequences

* Good, because the first page load after idle comes from the CDN, and the cold start waits for
  the first API call instead of the first byte.
* Good, because a deploy does not break a tab that is already open.
* Good, because static traffic costs CDN egress rather than container requests.
* Good, because the REST service is reachable only through the load balancer, which is the one
  place to attach Cloud Armor or rate limits later.
* Bad, because the GCP target now has a load balancer, a forwarding rule, a certificate, a bucket
  and a URL map where ADR-0017 had a container and a URL. The load balancer carries a fixed hourly
  charge whatever the traffic — about $18 a month at list price, not verified against the current
  pricing page — on a target chosen for scaling to zero.
* Bad, because the deploy gains a step — extract and upload — that must run in the right order
  relative to the revision, and the security headers live in two serving paths that must agree.
* Neutral, because the MCP service is a separate Cloud Run service with its own public address, and
  this record does not place it behind the load balancer.

### Confirmation

* The URL map, backend bucket, CDN policy, error response policy and response headers are OpenTofu
  in `infra/`, reviewed as infrastructure.
* A test asserts the CSP and security headers the OpenTofu configures for the backend bucket equal
  the ones the REST service sends for `/app/`, read from their single source.
* A deployment check, run after each deploy, requests `/app/`, a deep link under it, a hashed
  asset of the previous build and `/readyz` through the public address, and asserts the status,
  the CSP header and the cache headers of each.
* Not gated in CI: CI runs no GCP deployment (ADR-0004), so whether the load balancer routes as
  declared is verified by the deployment check, not before merge.

## Pros and Cons of the Options

### A global external Application Load Balancer: `/app/*` to a backend bucket with Cloud CDN

* Good, because it meets every driver, in GA resources the OpenTofu Google provider declares:
  `custom_response_headers` on the backend bucket, `default_custom_error_response_policy` on the
  URL map, which the provider documents as supported only for global external Application Load
  Balancers (checked against the provider's documentation, 2026-10-01).
* Bad, because of the fixed load-balancer charge and the added deploy step.

### The REST service serves `/app/` on GCP as it does elsewhere

The strongest case: it already works, it is one serving path everywhere, and it adds no
infrastructure, no charge and no deploy step.

* Good, because every deployment would serve the client identically.
* Bad, because the first load after idle waits for a cold start on a target that scales to zero by
  design, and every asset is a container request.
* Bad, because each deploy replaces the files an open tab is still loading from.

### The same load balancer with Cloud CDN in front of Cloud Run, and no bucket

Cloud CDN can cache a serverless backend, so the files would come from the edge without a bucket
or an upload step, straight from the image.

* Good, because there is no second copy of the build to keep in step.
* Bad, because a cache miss still lands on the container, and after a deploy every file is a miss.
* Bad, because the origin only ever has the current build, so an evicted chunk of the previous one
  is gone, and the open-tab failure returns whenever the cache does not happen to hold it.

### Firebase Hosting, rewriting API paths to Cloud Run

Built for exactly this — a static site on a global CDN, with rewrites to Cloud Run on the same
domain — and with a generous free tier.

* Good, because it is less infrastructure to declare and costs nothing at low traffic.
* Bad, because it is a second product with its own project binding, CLI and release model; a
  release is a deploy-time act of the Firebase CLI rather than declared state in OpenTofu, against
  ADR-0016.
* Bad, because the limits that apply to its rewrites to Cloud Run — timeouts, which headers and
  cookies pass — could not be confirmed from its documentation, and the import page posts large
  bodies through exactly that path. Not rejected on those limits, which are unverified, but on
  the deployment model.

### A bucket and CDN on a separate origin, calling the API cross-origin

The common shape: `app.example.com` on a CDN, `api.example.com` on Cloud Run.

* Good, because it needs no load balancer in front of the API.
* Bad, because it brings CORS back, and a misconfigured CORS policy is an authorization bug —
  the reason ADR-0049 rejected a separately deployed client.
* Bad, because the client would have two addresses where the product has one `PUBLIC_BASE_URL`.

### The API moved under `/api/`, the client at the root

* Good, because the client would own the root URL.
* Bad, because it changes every published REST route, a breaking change to a published interface
  (ADR-0015), for a cosmetic gain.
* Bad, because `/.well-known/` must stay at the root anyway, so the split would never be clean.

## More Information

**Follow-on obligations.**

* The single source of the client's security headers, read by the REST service and by `infra/`.
* The deploy step: extract the build from the image, upload with per-file `Cache-Control`, keep
  the previous build, remove older ones.
* The post-deploy check in Confirmation.

**Reversal cost.** Low. The application does not know the load balancer exists: removing it and
pointing the public address at Cloud Run is an infrastructure change, and the REST service serves
`/app/` again as it does everywhere else.

Related: ADR-0017 (the target), ADR-0049 (the client and its single origin), ADR-0054 (where the
build comes from), ADR-0016 (OpenTofu).

## Revisit when

* The load balancer's fixed charge is a significant share of the target's cost while traffic is
  negligible, which reopens serving from the REST service until it is not.
* The MCP service needs to share the public address, which puts it behind the same load balancer
  and reopens the URL map.
* A second cloud target is maintained, whose own static-hosting answer is decided in its own
  record rather than by analogy.
