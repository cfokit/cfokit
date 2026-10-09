---
status: "proposed"
kind: "requirement-driven"
date: 2026-10-09
decision-makers: [Geoff]
---

# ADR-0065: Database connections are encrypted, and the server's certificate is not verified

**Requirements served:** `SOC2-14`.

## Context and Problem Statement

`SOC2-14` requires customer data to be encrypted in transit. On GCP every service and job reaches
Cloud SQL at its private address, `10.219.80.5`, through Direct VPC egress into the `cfokit`
network ([ADR-0060](0060-production-is-one-gcp-project-deployed-on-merge.md) § 4). The instance
accepts only encrypted connections (`ssl_mode = "ENCRYPTED_ONLY"`), and every connection string
asks for TLS with `sslmode=require`: the connection is encrypted, and the client does not check
that the certificate it is shown belongs to the instance.

Checking it would defend against one thing: a party able to intercept traffic between a Cloud Run
instance and the database inside that private network, and to present a certificate of its own.
What is on that network is fixed by configuration. The project runs no virtual machines, and
organization policy refuses one a public address; the network is peered only with Google's service
networking for Cloud SQL; and the only workloads with an interface on it are CFOKit's own services
and jobs.

What verification needs here was measured, from a job inside the network, against the instance's
CA certificate (2026-10-09):

* `sslmode=verify-full` to the private address fails: "server certificate for
  `1-7c4f8089-b274-4c0c-b561-13736dedbeef.us-central1.sql.goog` (and 1 other name) does not match
  host name `10.219.80.5`". The certificate names the instance's DNS name, not its address.
* `sslmode=verify-ca` succeeds: the chain verifies against the instance's CA and the connection
  proceeds to authentication.

## Decision Drivers

* Customer data is encrypted in transit (`SOC2-14`).
* Configuration is environment variables only, and secrets are containers whose values are set out
  of band ([ADR-0004](0004-portability-as-a-build-gate.md), [ADR-0016](0016-opentofu-single-cloud-target-iac.md)).
* No provider SDK in the application, and no second runtime per service.
* A control is worth what it defends against on this network, measured, not assumed.

## Considered Options

* Encrypted, the certificate not verified (`sslmode=require`)
* `verify-ca`, with the instance's CA mounted into every service and job
* `verify-full`, connecting by the instance's DNS name through a private DNS record
* The Cloud SQL Auth Proxy, or Google's connector library

## Decision Outcome

Chosen option: "Encrypted, the certificate not verified", because every connection is encrypted
as `SOC2-14` requires, and verification would defend only against an interceptor inside a private
network that nothing but CFOKit's own workloads can join.

> Every connection to the database is encrypted, and the instance refuses any that is not. The
> client does not verify the server's certificate.

### Consequences

* Good, because nothing changes: no certificate to distribute, no connection string to rewrite, no
  rotation to schedule.
* Good, because the application's database configuration stays one standard connection string.
* Bad, because a party that could intercept traffic inside the network could present its own
  certificate and read or alter a connection. Reaching that position requires changing the
  project's network or its policies, which is audited and alerted (`monitoring.tf`).
* Neutral, because a self-hosted deployment chooses its own `sslmode` in its `DATABASE_URL`;
  nothing here prevents `verify-full` where a deployment's network allows it.

### Confirmation

`tests/test_gcp_infrastructure.py` asserts that the instance accepts only encrypted connections,
and that no virtual machine in the project may have a public address. That the network holds
nothing but CFOKit's workloads is enforced by organization policy and review of `infra/gcp/`, not
by a test.

## Pros and Cons of the Options

### Encrypted, the certificate not verified

* Good, because it is what runs today, and it meets `SOC2-14`.
* Bad, because it does not authenticate the server, which matters only if something can stand
  between the client and the server on the private network.

### `verify-ca`, with the instance's CA mounted

The measured option that works with the address as it is.

* Good, because it authenticates the server against the instance's own CA, and the address stays.
* Bad, because every service and job needs the CA as a file: a secret mounted into each, a
  `sslrootcert` path in every connection string, and the strings in Secret Manager rewritten. The
  issuer's JDBC connection needs the same in its own syntax.
* Bad, because the CA is the instance's, so recreating or migrating the instance means
  redistributing it, and a missed service stops connecting.
* Bad, because `verify-ca` accepts any certificate the CA signed, for any instance it serves, so
  it authenticates the CA rather than this instance.

### `verify-full`, by the instance's DNS name

* Good, because it is the full check: chain and name.
* Bad, because the name, `….us-central1.sql.goog`, does not resolve inside the network without a
  private DNS zone and a record kept in step with the instance's address, and it needs the CA
  mounted as `verify-ca` does.

### The Cloud SQL Auth Proxy, or the connector library

* Good, because it gives verified TLS and IAM-authenticated connections without managing a CA.
* Bad, because the connector library is a provider SDK in the application, which ADR-0004 keeps
  out, and the proxy is a second container beside every service and job, with its own image to
  keep current.

## More Information

**Follow-on obligations.** None while this holds.

**Reversal cost.** Low. `verify-ca` is a mounted secret and rewritten connection strings; it can
be adopted without changing the application.

## Revisit when

* Anything other than CFOKit's services and jobs gets an interface on the `cfokit` network: a
  virtual machine, another product's workload, or a new peering.
* A customer, an examiner or a provider's security review requires the database server's identity
  to be verified.
* Cloud SQL issues server certificates that name the private address, or the instance's DNS name
  becomes resolvable inside the network without a record of our own.
