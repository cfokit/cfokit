import { useEffect, useState } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useApi } from "../api";
import { ActionBar, Button, Notice } from "../components";
import { AgentNotices } from "../agents/AgentNotices";
import { describeAgent, signedInAs, useAgentConnections, when } from "../agents/name";
import { ConnectClaude } from "../connect/ConnectClaude";
import { PersonFrame } from "./PersonFrame";

/** A company the person can reach, as `GET /entities` lists it. */
export interface Company {
  id: string;
  slug: string;
  name: string;
  accounting_basis: string;
  fiscal_year_end_month: number;
  fiscal_year_end_day: number;
  functional_currency: string;
  time_zone: string;
}

const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

/** What a company declared when it was created, in the person's words. */
export function declared(company: Company): string {
  const basis = company.accounting_basis === "cash" ? "Cash basis" : "Accrual basis";
  const yearEnd = `${MONTHS[company.fiscal_year_end_month - 1]} ${company.fiscal_year_end_day}`;
  return `${basis} · year ends ${yearEnd} · ${company.functional_currency} · ${company.time_zone}`;
}

export type Listing =
  | { state: "loading" }
  | { state: "ready"; companies: Company[] }
  | { state: "failed"; message: string };

export function useCompanies(): Listing {
  const api = useApi();
  const [listing, setListing] = useState<Listing>({ state: "loading" });
  useEffect(() => {
    let current = true;
    api
      .get<{ entities: Company[] }>("/entities")
      .then((answer) => {
        if (current) setListing({ state: "ready", companies: answer.entities });
      })
      .catch((error: unknown) => {
        if (current) {
          setListing({
            state: "failed",
            message: error instanceof Error ? error.message : String(error),
          });
        }
      });
    return () => {
      current = false;
    };
  }, [api]);
  return listing;
}

function Companies() {
  const listing = useCompanies();
  const navigate = useNavigate();
  if (listing.state === "loading") {
    return (
      <Notice tone="neutral" label="Finding your companies">
        Reading which books you can reach…
      </Notice>
    );
  }
  if (listing.state === "failed") {
    return (
      <Notice tone="danger" label="Your companies could not be listed">
        {listing.message}
      </Notice>
    );
  }
  return (
    <>
      {listing.companies.length === 0 ? (
        <p className="text-body text-ink">You do not hold the books of any company yet.</p>
      ) : (
        <ul aria-label="Companies" className="flex flex-col border-t border-rule">
          {listing.companies.map((company) => (
            <li
              key={company.id}
              className="flex flex-col gap-2 border-b border-rule py-4 tablet:flex-row tablet:items-center tablet:justify-between"
            >
              <div className="flex min-w-0 flex-col gap-1">
                <span className="text-title text-ink">{company.name}</span>
                <span className="text-caption text-ink-muted">{declared(company)}</span>
              </div>
              <Button
                variant="link"
                onClick={() =>
                  void navigate({
                    to: "/companies/$entityId/questions",
                    params: { entityId: company.id },
                  })
                }
              >
                Questions
              </Button>
            </li>
          ))}
        </ul>
      )}
      <ActionBar>
        <Button
          variant="secondary"
          fullWidth
          className="tablet:w-auto"
          onClick={() => void navigate({ to: "/" })}
        >
          Add a company
        </Button>
      </ActionBar>
    </>
  );
}

type Allowed =
  | { state: "loading" }
  | { state: "ready"; agents: string[] }
  | { state: "failed"; message: string };

/** Every agent allowed in any of these companies, once each (ADR-0066 § 2). */
function useAllowedAgents(companies: Company[]): Allowed {
  const api = useApi();
  const [allowed, setAllowed] = useState<Allowed>({ state: "loading" });
  useEffect(() => {
    let current = true;
    Promise.all(
      companies.map((company) =>
        api
          .get<{ grants: { principal_id: string }[] }>(`/entities/${company.id}/grants`)
          // A company the person cannot grant in has no agents of theirs to manage.
          .catch(() => ({ grants: [] })),
      ),
    )
      .then((answers) => {
        if (!current) return;
        const agents = new Set(
          answers.flatMap((answer) =>
            answer.grants
              .map((held) => held.principal_id)
              .filter((principal) => principal.startsWith("client:")),
          ),
        );
        setAllowed({ state: "ready", agents: [...agents].sort() });
      })
      .catch((error: unknown) => {
        if (current) {
          setAllowed({
            state: "failed",
            message: error instanceof Error ? error.message : String(error),
          });
        }
      });
    return () => {
      current = false;
    };
  }, [api, companies]);
  return allowed;
}

function Agents({ companies }: { companies: Company[] }) {
  const allowed = useAllowedAgents(companies);
  const connections = useAgentConnections(companies);
  const navigate = useNavigate();
  if (allowed.state === "loading") {
    return <p className="text-caption text-ink-muted">Checking which agents you allowed…</p>;
  }
  if (allowed.state === "failed") {
    return (
      <Notice tone="danger" label="Your agents could not be listed">
        {allowed.message}
      </Notice>
    );
  }
  if (allowed.agents.length === 0) {
    return <p className="text-body text-ink">No agent is allowed in your companies yet.</p>;
  }
  return (
    <ul aria-label="Agents" className="flex flex-col border-t border-rule">
      {allowed.agents.map((agent) => {
        const connection = connections.get(agent);
        const account = connection === undefined ? null : signedInAs(connection);
        return (
          <li
            key={agent}
            className="flex items-center justify-between gap-2 border-b border-rule py-4"
          >
            <span className="flex min-w-0 flex-col">
              <span className="text-body text-ink">{describeAgent(agent, connection)}</span>
              {connection !== undefined && (
                <span className="text-caption text-ink-muted">
                  {account === null ? "" : `Signed in as ${account}. `}Last connected{" "}
                  {when(connection.last_connected_at)}.
                </span>
              )}
            </span>
            <Button
              variant="link"
              onClick={() => void navigate({ to: "/agents/$agent", params: { agent } })}
            >
              Manage
            </Button>
          </li>
        );
      })}
    </ul>
  );
}

function AgentsSection() {
  const listing = useCompanies();
  if (listing.state !== "ready" || listing.companies.length === 0) return null;
  return (
    <section aria-labelledby="agents" className="flex flex-col gap-4">
      <h2 id="agents" className="font-display text-heading text-ink">
        Agents
      </h2>
      <p className="text-body text-ink">
        An agent acts only in the companies you allowed it in. Manage one to allow or revoke it.
      </p>
      <AgentNotices companies={listing.companies} />
      <Agents companies={listing.companies} />
    </section>
  );
}

/** The person's settings: the companies they hold, and how to connect Claude, at any time. */
export function SettingsPage() {
  return (
    <PersonFrame company="">
      <div className="flex max-w-reading-max flex-col gap-6">
        <h1 className="font-display text-display-compact text-ink tablet:text-display">Settings</h1>
        <section aria-labelledby="companies" className="flex flex-col gap-4">
          <h2 id="companies" className="font-display text-heading text-ink">
            Companies
          </h2>
          <Companies />
        </section>
        <section aria-labelledby="connect" className="flex flex-col gap-4">
          <h2 id="connect" className="font-display text-heading text-ink">
            Connect Claude
          </h2>
          <p className="text-body text-ink">
            One connection serves all your companies, and acts only in the ones you allow it in.
            Claude asks which company you mean when more than one fits.
          </p>
          <ConnectClaude />
        </section>
        <AgentsSection />
      </div>
    </PersonFrame>
  );
}
