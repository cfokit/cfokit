import { useEffect, useState } from "react";
import { useApi } from "../api";

/** An agent that has connected for the person, as `GET /agents` lists it (ADR-0066 § 3). */
export interface AgentConnection {
  agent_id: string;
  client_name: string | null;
  client_version: string | null;
  person_email: string | null;
  person_name: string | null;
  first_connected_at: string;
  last_connected_at: string;
}

/** The client's ID alone: how an agent is named when nothing else is known of it. */
export function agentName(agent: string): string {
  return agent.startsWith("client:") ? `Client ${agent.slice("client:".length)}` : agent;
}

/**
 * How an agent is named to the person: what the client reported when it connected, or its ID
 * where it reported nothing or never connected for them. The reported name is the client's own
 * claim, so it labels the agent and never stands in for the grant.
 */
export function describeAgent(agent: string, connection: AgentConnection | undefined): string {
  if (connection?.client_name == null) return agentName(agent);
  return connection.client_version == null
    ? connection.client_name
    : `${connection.client_name} ${connection.client_version}`;
}

/** The account an agent signed in as, by name and email where the issuer sent them. */
export function signedInAs(connection: AgentConnection): string | null {
  const { person_name: name, person_email: email } = connection;
  if (name != null && email != null) return `${name} (${email})`;
  return name ?? email;
}

/** A moment, in the person's own locale and time zone. */
export function when(moment: string): string {
  return new Date(moment).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

/**
 * Every agent the person can know of, by agent ID: those that connected for them (`GET /agents`),
 * then those allowed in companies they administer, as each connected for a member there
 * (`GET /entities/{id}/agents`). Their own record wins where both have one. Empty until the
 * answers arrive, and any that fails is left out: a name is a label, and every agent is still
 * shown by its ID without one.
 */
export function useAgentConnections(
  companies: readonly { id: string }[] = [],
): Map<string, AgentConnection> {
  const api = useApi();
  const [connections, setConnections] = useState<Map<string, AgentConnection>>(new Map());
  useEffect(() => {
    let current = true;
    const read = (path: string) =>
      api
        .get<{ agents?: AgentConnection[] }>(path)
        .then((answer) => answer.agents ?? [])
        .catch((): AgentConnection[] => []);
    Promise.all([
      read("/agents"),
      ...companies.map((company) => read(`/entities/${encodeURIComponent(company.id)}/agents`)),
    ])
      .then(([own = [], ...elsewhere]) => {
        if (!current) return;
        const known = new Map<string, AgentConnection>();
        for (const found of elsewhere.flat()) known.set(found.agent_id, found);
        for (const found of own) known.set(found.agent_id, found);
        setConnections(known);
      })
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [api, companies]);
  return connections;
}
