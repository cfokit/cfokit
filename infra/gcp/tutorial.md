# Deploy CFOKit to Google Cloud

<walkthrough-tutorial-duration duration="60"></walkthrough-tutorial-duration>

This puts CFOKit into production in a Google Cloud project of yours, the way
[ADR-0060](https://github.com/cfokit/cfokit/blob/main/docs/decisions/0060-production-is-one-gcp-project-deployed-on-merge.md)
describes it:

* one load balancer serving three hostnames you own: `app.`, `mcp.` and `auth.` your domain;
* the REST and MCP services and the issuer (Keycloak) on Cloud Run;
* PostgreSQL on Cloud SQL, reachable only on a private address;
* a deploy on every merge to `main` of your repository, signed in without keys.

Every step runs a script in `infra/gcp/setup/`, and every script is safe to run again. **No
password is ever shown to you or written to a file**: each is generated and piped straight into
Secret Manager.

You will need:

* a Google Cloud project with billing linked, which you own;
* a domain whose DNS you can edit;
* your fork of `cfokit/cfokit` on GitHub (or this repository, if you are CFOKit).

Click **Start**.

## Name the deployment

<walkthrough-project-setup billing="true"></walkthrough-project-setup>

Replace the values with yours: the project, your domain, a region, and the GitHub repository whose
`main` branch will deploy.

```sh
infra/gcp/setup/configure.sh <walkthrough-project-id/> example.com us-central1 your-github-name/cfokit
```

Nothing secret is recorded: only names, in `~/.config/cfokit/deploy.env`.

## Install OpenTofu

Cloud Shell has Terraform, not OpenTofu. CFOKit uses OpenTofu, whose license lets you run what it
ships ([ADR-0016](https://github.com/cfokit/cfokit/blob/main/docs/decisions/0016-opentofu-single-cloud-target-iac.md)).

```sh
curl --proto '=https' --tlsv1.2 -fsSL https://get.opentofu.org/install-opentofu.sh -o /tmp/install-opentofu.sh
sh /tmp/install-opentofu.sh --install-method deb && tofu version
```

## Check the project

Confirms you are signed in, the project exists and billing is linked. If anything is missing it
says exactly what to run.

```sh
infra/gcp/setup/project.sh
```

## Where the infrastructure's state lives

A versioned bucket for OpenTofu's state, and a Cloud KMS key the state is encrypted with, so the
bucket alone reveals nothing.

```sh
infra/gcp/setup/state.sh
```

## Network, database and identities

The network, the Cloud SQL instance and its two databases, the secret containers (empty), and one
identity per service. **This takes 10 to 15 minutes**, almost all of it the database.

```sh
infra/gcp/setup/foundation.sh
```

## Database roles and secrets

Creates the three database roles and fills every secret. The application's role is made with
SQL from a one-off job inside the network, so row-level security applies to it.

```sh
infra/gcp/setup/database.sh
```

The issuer's first administrator is `admin`. You will want the password once, to replace that
account with a named one; this prints it to your terminal only:

```sh
gcloud secrets versions access latest --secret keycloak-admin-password; echo
```

## Build the images

Builds the application and issuer images from this checkout and pushes them. **Around ten
minutes**; set your DNS records (next step but one) while it runs, in a second terminal tab.

```sh
infra/gcp/setup/images.sh --latest
```

## Services and the load balancer

The REST, MCP and issuer services, the migration job, the web bucket behind Cloud CDN, and the
load balancer with its certificate.

```sh
infra/gcp/setup/apply.sh
```

## DNS

Prints four A records: `app`, `mcp`, `auth`, and `admin`, the issuer's admin console, which only accounts you name can reach. Add them at your DNS provider **with any proxy turned off** — at
Cloudflare, "DNS only", the grey cloud — so Google's certificate can validate each name.

```sh
infra/gcp/setup/dns.sh
```

Then wait for them to resolve and the certificate to become active. That can take up to an hour;
the script returns when it is done.

```sh
infra/gcp/setup/dns.sh --wait
```

## First deploy

Runs the migrations, publishes the web client, rolls out the services on the images you built,
and checks every hostname from the outside.

```sh
infra/gcp/setup/deploy.sh
```

## The issuer's settings

Points the master realm, which holds the issuer's administrators, at the admin console's own
host, without which the console cannot finish signing in; and sets the lockout, password policy,
events and token lifetime on both realms. It signs in as a temporary administrator it creates and
deletes, so no password is needed.

```sh
infra/gcp/setup/realm.sh --settings
```

## Deploy on every merge

Tells your repository's deploy workflow where to deploy. These are names, not secrets: the
workflow signs in through Workload Identity Federation, which trusts your repository's `main`
branch and nothing else.

```sh
infra/gcp/setup/github.sh
```

If `gh` is not signed in here, it prints the five variables and the page to add them on.

## Done

<walkthrough-conclusion-trophy></walkthrough-conclusion-trophy>

CFOKit is at `https://app.` your domain. Create your account there, then follow getting started
to import your books and connect your agent.

From here:

* **Code** reaches production on every merge to `main`.
* **Infrastructure** changes are pull requests to `infra/gcp/`, applied with
  `infra/gcp/setup/apply.sh` by a person; the deploy pipeline never changes infrastructure.
* **A rollback** is `gcloud run services update-traffic` to the previous revision. Migrations
  only go forward.
