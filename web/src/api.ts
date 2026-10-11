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
  /** `headers` carries what a write needs besides its body, such as its `Idempotency-Key`. */
  post<T>(path: string, body: unknown, headers?: Record<string, string>): Promise<T>;
  /** Ends something, such as a grant; the API answers with no body. */
  delete(path: string): Promise<void>;
}

async function refusal(response: Response): Promise<ApiError> {
  const payload: unknown = await response.json().catch(() => null);
  const problem = (payload ?? {}) as { code?: unknown; message?: unknown };
  return new ApiError(
    response.status,
    typeof problem.code === "string" ? problem.code : "unexpected",
    typeof problem.message === "string" ? problem.message : response.statusText,
  );
}

async function answer<T>(response: Response): Promise<T> {
  if (!response.ok) throw await refusal(response);
  return (await response.json().catch(() => null)) as T;
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
      async post<T>(path: string, body: unknown, headers: Record<string, string> = {}): Promise<T> {
        return answer<T>(
          await fetch(path, {
            method: "POST",
            headers: { "content-type": "application/json", ...headers, ...authorization },
            body: JSON.stringify(body),
          }),
        );
      },
      async delete(path: string): Promise<void> {
        const response = await fetch(path, { method: "DELETE", headers: authorization });
        if (!response.ok) throw await refusal(response);
      },
    };
  }, [token]);
}
