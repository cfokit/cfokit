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
  post<T>(path: string, body: unknown): Promise<T>;
}

/**
 * The published REST API on this origin, called with the signed-in person's token, like any other
 * client (ADR-0049 § 4).
 */
export function useApi(): Api {
  const token = useAuth().user?.access_token;
  return useMemo(
    () => ({
      async post<T>(path: string, body: unknown): Promise<T> {
        const response = await fetch(path, {
          method: "POST",
          headers: {
            "content-type": "application/json",
            ...(token === undefined ? {} : { authorization: `Bearer ${token}` }),
          },
          body: JSON.stringify(body),
        });
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
      },
    }),
    [token],
  );
}
