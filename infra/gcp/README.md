# Production on GCP

OpenTofu for the maintained cloud target ([ADR-0017](../../docs/decisions/0017-gcp-initial-cloud-target.md),
[ADR-0055](../../docs/decisions/0055-on-gcp-the-web-client-is-served-from-a-cdn.md),
[ADR-0060](../../docs/decisions/0060-production-is-one-gcp-project-deployed-on-merge.md)). It
meets the contract in [`infra/README.md`](../README.md) and nothing more: the application does
not know it is on GCP.

| File | What it declares |
|---|---|
| `versions.tf` | The provider, the state backend, and state encryption with Cloud KMS |
| `variables.tf` | Project, region, zone, domain, the repository allowed to deploy, and who is let into the admin console and alerted |
| `main.tf` | APIs, and the image repository |
| `network.tf` | The VPC, the subnet services egress into, and private services access |
| `database.tf` | The Cloud SQL instance and its two databases |
| `secrets.tf` | Secret containers. Never values |
| `iam.tf` | One identity per runtime, the deploy identity, and GitHub federation |
| `run.tf` | The REST, MCP and issuer services, and the migration job |
| `loadbalancer.tf` | The web bucket and CDN, the load balancer, the certificate |
| `armor.tf` | Cloud Armor: rate limits on sign-in and the API |
| `audit.tf` | Which reads are audit-logged, and how long logs are kept |
| `monitoring.tf` | Alerts per event class, and uptime checks, emailed to `alert_emails` |
| `outputs.tf` | What the first-time steps and the deploy workflow need |

**A person applies this; the deploy pipeline never does** (ADR-0060 § 6). The pipeline,
`.github/workflows/deploy.yml`, ships application code on every merge to `main`.

## First time

[![Open in Cloud Shell](https://gstatic.com/cloudssh/images/open-btn.svg)](https://shell.cloud.google.com/cloudshell/editor?cloudshell_git_repo=https://github.com/cfokit/cfokit&cloudshell_git_branch=main&cloudshell_tutorial=infra/gcp/tutorial.md&show=terminal)

The button clones the repository into Cloud Shell and opens [`tutorial.md`](tutorial.md) beside
it, a step at a time. A fork deploys from its own repository: change `cfokit/cfokit` in the link,
or clone it into Cloud Shell yourself and run `cloudshell launch-tutorial infra/gcp/tutorial.md`.

The tutorial runs the scripts in [`setup/`](setup/), in order, and they run the same anywhere
`gcloud`, OpenTofu, Docker and `dig` are installed:

| Script | What it does |
|---|---|
| `configure.sh PROJECT DOMAIN [REGION] [REPO]` | Records the deployment's names in `~/.config/cfokit/deploy.env` |
| `project.sh` | Checks sign-in, the project and billing |
| `state.sh` | The state bucket and its KMS key, then `tofu init` |
| `foundation.sh` | Network, database, secret containers, identities |
| `database.sh` | Database roles and every secret's value, none of them ever printed |
| `images.sh [--latest] [COMMIT]` | Build and push both images, tagged with the commit (and `latest`, before the first apply) |
| `apply.sh` | Services, the migration job, the web bucket, the load balancer |
| `dns.sh [--wait]` | The three A records to set; waits for them and the certificate |
| `deploy.sh [COMMIT]` | Build, migrate, publish the web build, roll out, check |
| `github.sh` | The deploy workflow's repository variables |
| `realm.sh --settings [COMMIT]` | Apply the realms' settings in place, keeping every account; once after the first deploy |
| `realm.sh --replace [COMMIT]` | Replace the issuer's realm with the image's, removing its accounts |

`deploy.sh` is also what `.github/workflows/deploy.yml` runs on every merge, so the first deploy
and every later one are the same code.

## Afterwards

* **Infrastructure changes** are pull requests to this directory, reviewed under the code-owner
  rule, then `tofu plan` and `tofu apply` by a person.
* **A secret rotates** by adding a version and redeploying the services that read it; nothing in
  OpenTofu changes.
* **A realm change** in `infra/keycloak/cfokit-realm.json` does not reach a running deployment
  by itself, because Keycloak imports a realm only when it does not exist. A change to a value
  `infra/keycloak/realm-settings.sh` sets reaches it through `setup/realm.sh --settings`, which
  keeps every account; anything else through `setup/realm.sh --replace`, which removes them.
* **A rollback** is `gcloud run services update-traffic` to the previous revision. A migration is
  not rolled back: migrations are written forward-only.
