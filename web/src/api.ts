import { useMemo } from "react";
import { useAuth } from "react-oidc-context";

/** A refusal from the API: its machine-readable `code` is the contract (ADR-0015). */
export class ApiError extends Error {
  constructor(
    readonly status: number,
    readonly code: string,
    message: string,
  ) {
    super(message);
  }
}

export interface Api {
  get<T>(path: string): Promise<T>;
  post<T>(path: string, body: unknown): Promise<T>;
}

async function answer<T>(response: Response): Promise<T> {
  const payload: unknown = await response.json().catch(() => null);
  if (!response.ok) {
    const problem = (payload ?? {}) as { code?: unknown; message?: unknown };
    throw new ApiError(
      response.status,
      typeof problem.code === "string" ? problem.code : "unexpected",
      typeof problem.message === "string" ? problem.message : response.statusText,
    );
  }
  return payload as T;
}

/**
 * The published REST API on this origin, called with the signed-in person's token, like any other
 * client (ADR-0049 § 4).
 */
export function useApi(): Api {
  const token = useAuth().user?.access_token;
  return useMemo(() => {
    const authorization: Record<string, string> =
      token === undefined ? {} : { authorization: `Bearer ${token}` };
    return {
      async get<T>(path: string): Promise<T> {
        return answer<T>(await fetch(path, { headers: authorization }));
      },
      async post<T>(path: string, body: unknown): Promise<T> {
        return answer<T>(
          await fetch(path, {
            method: "POST",
            headers: { "content-type": "application/json", ...authorization },
            body: JSON.stringify(body),
          }),
        );
      },
    };
  }, [token]);
}
