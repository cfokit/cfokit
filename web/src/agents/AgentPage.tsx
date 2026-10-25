import { useEffect, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { ApiError, useApi } from "../api";
import { Button, Notice } from "../components";
import { AGENT } from "../chat/agentUrl";
import { PersonFrame } from "../settings/PersonFrame";
import { describeAgent, signedInAs, useAgentConnections, when, type AgentConnection } from "./name";
import { useCompanies, type Company } from "../settings/SettingsPage";

/** A grant in force, as `GET /entities/{id}/grants` lists it. */
export interface Grant {
  grant_id: string;
  principal_id: string;
  role: string;
  granted_by: string;
  granted_at: string;
  lapses_at: string | null;
}

/** The two roles a person allows an agent in (ADR-0066 § 2), in the person's words. */
export const AGENT_ROLES: Record<string, string> = {
  reader: "Reads the books",
  bookkeeper: "Keeps the books: reads, records and posts",
};

/** How each role is offered once the agent holds another (ADR-0073), in the order shown. */
const ALSO_ALLOW: [role: string, label: string][] = [
  ["bookkeeper", "Also allow to keep the books"],
  ["reader", "Also allow to read only"],
];

const NO_COMPANIES: Company[] = [];

type Standing =
  | { state: "loading" }
  | { state: "allowed"; grants: Grant[] }
  | { state: "not-allowed" }
  | { state: "cannot-grant" }
  | { state: "failed"; message: string };

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/**
 * Where this agent stands in one company: every role it holds there, each removable, and the
 * roles it could be given besides (ADR-0073).
 */
function CompanyRow({
  company,
  agent,
  draft,
}: {
  company: Company;
  agent: string;
  draft: string | undefined;
}) {
  const api = useApi();
  const [standing, setStanding] = useState<Standing>({ state: "loading" });
  const [busy, setBusy] = useState(false);
  // Set when the person allows the agent here, on this visit: then the page says what is next.
  const [justAllowed, setJustAllowed] = useState(false);
  const navigate = useNavigate();

  // Bumped after each change, so the standing is read again from the server, which holds it.
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let current = true;
    api
      .get<{ grants: Grant[] }>(`/entities/${company.id}/grants`)
      .then((answer) => {
        if (!current) return;
        const grants = answer.grants.filter((held) => held.principal_id === agent);
        setStanding(grants.length === 0 ? { state: "not-allowed" } : { state: "allowed", grants });
      })
      .catch((error: unknown) => {
        if (!current) return;
        setStanding(
          error instanceof ApiError && error.status === 403
            ? { state: "cannot-grant" }
            : { state: "failed", message: messageOf(error) },
        );
      });
    return () => {
      current = false;
    };
  }, [api, company.id, agent, version]);

  async function act(change: () => Promise<unknown>) {
    setBusy(true);
    try {
      await change();
      setVersion((count) => count + 1);
    } catch (error) {
      setStanding({ state: "failed", message: messageOf(error) });
    } finally {
      setBusy(false);
    }
  }

  const allow = (role: string) =>
    act(async () => {
      await api.post(`/entities/${company.id}/grants`, { principal_id: agent, role });
      setJustAllowed(true);
    });
  const remove = (grant: Grant) =>
    act(async () => {
      await api.delete(`/entities/${company.id}/grants/${grant.grant_id}`);
      setJustAllowed(false);
    });

  return (
    <li className="flex flex-col gap-3 border-b border-rule py-4">
      <span className="text-title text-ink">{company.name}</span>
      {standing.state === "loading" && <p className="text-caption text-ink-muted">Checking…</p>}
      {standing.state === "allowed" && (
        <div className="flex flex-col gap-2">
          <ul aria-label={`Roles in ${company.name}`} className="flex flex-col gap-2">
            {standing.grants.map((grant) => (
              <li
                key={grant.grant_id}
                className="flex flex-col gap-2 tablet:flex-row tablet:items-center tablet:justify-between"
              >
                <p className="text-body text-ink">
                  Allowed. {AGENT_ROLES[grant.role] ?? grant.role}.
                </p>
                <Button variant="destructive" disabled={busy} onClick={() => void remove(grant)}>
                  Remove
                </Button>
              </li>
            ))}
          </ul>
          <div className="flex flex-col gap-2 tablet:flex-row">
            {ALSO_ALLOW.filter(([role]) => !standing.grants.some((g) => g.role === role)).map(
              ([role, label]) => (
                <Button
                  key={role}
                  variant="secondary"
                  disabled={busy}
                  onClick={() => void allow(role)}
                >
                  {label}
                </Button>
              ),
            )}
          </div>
        </div>
      )}
      {standing.state === "allowed" && justAllowed && agent !== AGENT && (
        <Notice tone="success" label="Done" announce>
          Go back to Claude and ask again. It can act in {company.name} now.
        </Notice>
      )}
      {standing.state === "allowed" && justAllowed && agent === AGENT && (
        // CFOKit's own agent is answered in the web client, so the way back is to its chat, with
        // what the person had written there (ADR-0068 § 3).
        <Notice tone="success" label="Done" announce>
          <p>CFOKit can act in {company.name} now.</p>
          <div className="pt-2">
            <Button
              variant="primary"
              onClick={() =>
                void navigate({
                  to: "/companies/$entityId/chat",
                  params: { entityId: company.id },
                  search: draft === undefined ? {} : { draft },
                })
              }
            >
              Ask CFOKit
            </Button>
          </div>
        </Notice>
      )}
      {standing.state === "not-allowed" && (
        <div className="flex flex-col gap-2 tablet:flex-row">
          <Button variant="primary" disabled={busy} onClick={() => void allow("bookkeeper")}>
            Allow to keep the books
          </Button>
          <Button variant="secondary" disabled={busy} onClick={() => void allow("reader")}>
            Allow to read only
          </Button>
        </div>
      )}
      {standing.state === "cannot-grant" && (
        <p className="text-caption text-ink-muted">
          Only someone who administers this company can allow an agent in it.
        </p>
      )}
      {standing.state === "failed" && (
        <Notice tone="danger" label="This company could not be changed">
          {standing.message}
        </Notice>
      )}
    </li>
  );
}

/**
 * What is known of the agent, so the person can tell it is the one they just connected: what it
 * reported itself as, the account it signed in as, and when (ADR-0066 § 3).
 */
function AgentFacts({
  agent,
  connection,
}: {
  agent: string;
  connection: AgentConnection | undefined;
}) {
  const account = connection === undefined ? null : signedInAs(connection);
  return (
    <dl aria-label="This agent" className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1 text-body">
      {connection === undefined ? (
        <>
          <dt className="text-ink-muted">Connected</dt>
          <dd className="text-ink">
            CFOKit has no record of it connecting for you or anyone in your companies.
          </dd>
        </>
      ) : (
        <>
          {account !== null && (
            <>
              <dt className="text-ink-muted">Signed in as</dt>
              <dd className="text-ink">{account}</dd>
            </>
          )}
          <dt className="text-ink-muted">First connected</dt>
          <dd className="text-ink">{when(connection.first_connected_at)}</dd>
          <dt className="text-ink-muted">Last connected</dt>
          <dd className="text-ink">{when(connection.last_connected_at)}</dd>
        </>
      )}
      <dt className="text-ink-muted">Client ID</dt>
      <dd className="break-all text-ink">{agent.replace(/^client:/, "")}</dd>
    </dl>
  );
}

/**
 * Allowing an agent, company by company (ADR-0066 § 2). An agent acts in a company only where the
 * person allowed it there; this is where they do, signed in as themselves (`IAM-10`, `IAM-12`).
 * Every refusal an agent receives for want of it links here.
 */
export function AgentPage({ agent, draft }: { agent: string; draft?: string | undefined }) {
  const listing = useCompanies();
  const navigate = useNavigate();
  const connection = useAgentConnections(
    listing.state === "ready" ? listing.companies : NO_COMPANIES,
  ).get(agent);
  return (
    <PersonFrame company="">
      <div className="flex max-w-reading-max flex-col gap-6">
        <div className="-mx-3">
          <Button variant="link" onClick={() => void navigate({ to: "/settings" })}>
            ← Back to Settings
          </Button>
        </div>
        <h1 className="font-display text-display-compact text-ink tablet:text-display">Agent</h1>
        <p className="text-body text-ink">
          {describeAgent(agent, connection)} is software you signed in to CFOKit through, such as
          Claude. It acts only in the companies you allow it in below, and never with more authority
          than you hold.
        </p>
        <AgentFacts agent={agent} connection={connection} />
        {listing.state === "loading" && (
          <Notice tone="neutral" label="Finding your companies">
            Reading which books you can reach…
          </Notice>
        )}
        {listing.state === "failed" && (
          <Notice tone="danger" label="Your companies could not be listed">
            {listing.message}
          </Notice>
        )}
        {listing.state === "ready" &&
          (listing.companies.length === 0 ? (
            <p className="text-body text-ink">You do not hold the books of any company yet.</p>
          ) : (
            <ul aria-label="Companies" className="flex flex-col border-t border-rule">
              {listing.companies.map((company) => (
                <CompanyRow key={company.id} company={company} agent={agent} draft={draft} />
              ))}
            </ul>
          ))}
      </div>
    </PersonFrame>
  );
}
