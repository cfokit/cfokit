# Run CFOKit on your computer

From nothing to asking Claude about your books, on one machine and with no cloud account. It takes
about fifteen minutes.

> **Tested on macOS.** The certificate-trust command and Claude Desktop's config path are macOS's.
> Windows and Linux are untested, so expect to adapt those steps.

You need [Docker](https://docs.docker.com/get-docker/), with the daemon running, and
[Claude Desktop](https://claude.com/download).

## 1. Start CFOKit

From the folder you cloned CFOKit into:

```bash
docker compose up -d --wait                       # Postgres, the sign-in service, the web app, MCP
docker compose --profile migrate run --rm migrate # create the schema; never runs on startup
```

Everything serves HTTPS from a certificate authority the stack generates in `.local/tls/`. Trust it
once, so your browser opens the pages without a warning. macOS asks for your password:

```bash
security add-trusted-cert -r trustRoot -k ~/Library/Keychains/login.keychain-db .local/tls/ca/ca.pem
```

It stays trusted until you delete `.local/tls/`, which makes a new one on the next start.

On Windows, also add `127.0.0.1 keycloak.localhost` to your hosts file.

## 2. Create your account

Open **https://localhost:8080/app/**, choose **Register** on the sign-in page, and create your
account with your email and a password. Claude signs in as this account later.

## 3. Bring in your books

Getting started asks for your QuickBooks Online export: the .zip from **Settings → Export data**,
all dates. It is read in your browser and never uploaded.

No export to hand? This writes a small synthetic one to `.local/quickbooks-sample.zip` (it needs
the Node version in `web/.nvmrc`):

```bash
cd web && corepack pnpm install && corepack pnpm sample-export
```

Confirm the company the export describes, then import. When it finishes, the page shows whether
the books agree with QuickBooks. [Reading an import](../explanation/reading-an-import.md) explains
any difference it reports.

## 4. Connect Claude

The next page gives the steps with this CFOKit's own addresses filled in: register Claude Desktop
as a client, add CFOKit to its configuration, and add the bookkeeper skill.
[Connect Claude](../how-to/connect-claude.md) explains each step.

You can find the same steps later under **Settings**, at the top right of every page.

## 5. Ask about your books

The last page has **Continue in Claude**. It opens Claude Desktop on a new chat, with a first
question about your company already written. Send it.

## Where things are

| | Address |
|---|---|
| The web app and the REST API | `https://localhost:8080` |
| The MCP endpoint Claude connects to | `https://localhost:8081/mcp` |
| The sign-in service | `https://keycloak.localhost:8443` |

This is the real thing, not a demo. The books live in a Docker volume, and
`docker compose down -v` destroys them.
