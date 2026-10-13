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
 * The agents that have connected for the person, by agent ID. Empty until the answer arrives,
 * and empty if it fails: a name is a label, and every agent is still shown by its ID without one.
 */
export function useAgentConnections(): Map<string, AgentConnection> {
  const api = useApi();
  const [connections, setConnections] = useState<Map<string, AgentConnection>>(new Map());
  useEffect(() => {
    let current = true;
    api
      .get<{ agents?: AgentConnection[] }>("/agents")
      .then((answer) => {
        if (!current) return;
        setConnections(new Map((answer.agents ?? []).map((found) => [found.agent_id, found])));
      })
      .catch(() => undefined);
    return () => {
      current = false;
    };
  }, [api]);
  return connections;
}
