/** How an agent is named to the person: the client they signed in through (ADR-0066). */
export function agentName(agent: string): string {
  return agent.startsWith("client:") ? `Client ${agent.slice("client:".length)}` : agent;
}
