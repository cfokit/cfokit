import { useEffect, useState } from "react";
import { useApi } from "../api";

/**
 * Where this deployment's agent is, as its operator configured it: `null` while asking,
 * `undefined` when the deployment runs none (ADR-0075 § 1).
 */
export function useAgentUrl(): string | null | undefined {
  const api = useApi();
  const [url, setUrl] = useState<string | null | undefined>(null);
  useEffect(() => {
    let current = true;
    api
      .get<{ agent_url?: string | null }>("/connection")
      .then((connection) => {
        if (current) setUrl(connection.agent_url ?? undefined);
      })
      .catch(() => {
        if (current) setUrl(undefined);
      });
    return () => {
      current = false;
    };
  }, [api]);
  return url;
}
