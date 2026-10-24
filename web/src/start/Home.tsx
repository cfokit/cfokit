import { useEffect } from "react";
import { useNavigate } from "@tanstack/react-router";
import { useAgentUrl } from "../chat/agentUrl";
import { useCompanies } from "../settings/SettingsPage";
import { GettingStarted } from "./GettingStarted";

/**
 * Where a signed-in person lands. Someone with a company goes to its chat with CFOKit, where the
 * deployment runs CFOKit's agent: that is a company's home in the web client (ADR-0068 § 3).
 * Someone with none, or on a deployment with no agent, gets getting started (ADR-0058).
 */
export function Home() {
  const listing = useCompanies();
  const agentUrl = useAgentUrl();
  const navigate = useNavigate();
  const first = listing.state === "ready" ? listing.companies[0] : undefined;

  useEffect(() => {
    if (first !== undefined && typeof agentUrl === "string") {
      void navigate({
        to: "/companies/$entityId/chat",
        params: { entityId: first.id },
        replace: true,
      });
    }
  }, [first, agentUrl, navigate]);

  const deciding = listing.state === "loading" || (first !== undefined && agentUrl !== undefined);
  return deciding ? null : <GettingStarted />;
}
