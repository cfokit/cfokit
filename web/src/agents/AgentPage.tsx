import { useEffect, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { ApiError, useApi } from "../api";
import { Button, Notice } from "../components";
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

type Standing =
  | { state: "loading" }
  | { state: "allowed"; grant: Grant }
  | { state: "not-allowed" }
  | { state: "cannot-grant" }
  | { state: "failed"; message: string };

function messageOf(error: unknown): string {
  return error instanceof Error ? error.message : String(error);
}

/** Where this agent stands in one company, and the person's one action on it. */
function CompanyRow({ company, agent }: { company: Company; agent: string }) {
  const api = useApi();
  const [standing, setStanding] = useState<Standing>({ state: "loading" });
  const [busy, setBusy] = useState(false);
  // Set when the person allows the agent here, on this visit: then the page says what is next.
  const [justAllowed, setJustAllowed] = useState(false);

  // Bumped after each change, so the standing is read again from the server, which holds it.
  const [version, setVersion] = useState(0);

  useEffect(() => {
    let current = true;
    api
      .get<{ grants: Grant[] }>(`/entities/${company.id}/grants`)
      .then((answer) => {
        if (!current) return;
        const grant = answer.grants.find((held) => held.principal_id === agent);
        setStanding(grant === undefined ? { state: "not-allowed" } : { state: "allowed", grant });
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
  const revoke = (grant: Grant) =>
    act(async () => {
      await api.delete(`/entities/${company.id}/grants/${grant.grant_id}`);
      setJustAllowed(false);
    });

  return (
    <li className="flex flex-col gap-3 border-b border-rule py-4">
      <span className="text-title text-ink">{company.name}</span>
      {standing.state === "loading" && <p className="text-caption text-ink-muted">Checking…</p>}
      {standing.state === "allowed" && (
        <div className="flex flex-col gap-2 tablet:flex-row tablet:items-center tablet:justify-between">
          <p className="text-body text-ink">
            Allowed. {AGENT_ROLES[standing.grant.role] ?? standing.grant.role}.
          </p>
          <Button variant="destructive" disabled={busy} onClick={() => void revoke(standing.grant)}>
            Revoke
          </Button>
        </div>
      )}
      {standing.state === "allowed" && justAllowed && (
        <Notice tone="success" label="Done" announce>
          Go back to Claude and ask again. It can act in {company.name} now.
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
          <dd className="text-ink">CFOKit has no record of it signing in as you.</dd>
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
export function AgentPage({ agent }: { agent: string }) {
  const listing = useCompanies();
  const navigate = useNavigate();
  const connection = useAgentConnections().get(agent);
  return (
    <PersonFrame company="">
      <div className="flex max-w-reading-max flex-col gap-6">
        <div className="-mx-3">
          <Button variant="link" onClick={() => void navigate({ to: "/settings" })}>
            ← Back to Settings
          </Button>
        </div>
        <h1 className="font-display text-display-compact text-ink tablet:text-display">
          Allow an agent
        </h1>
        <p className="text-body text-ink">
          {describeAgent(agent, connection)} is software you signed in to CFOKit through, such as
          Claude. It can act only in the companies you allow it in, and never with more authority
          than you hold. If you did not just connect an agent, allow nothing.
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
                <CompanyRow key={company.id} company={company} agent={agent} />
              ))}
            </ul>
          ))}
      </div>
    </PersonFrame>
  );
}
