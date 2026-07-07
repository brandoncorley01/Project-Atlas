import { getApiUrl, usesBffProxy } from "@/lib/api-url";
import { API_START_HINT, apiPortLabel } from "@/lib/api-config";

const DEFAULT_TIMEOUT_MS = 90_000;

export class ApiError extends Error {
  status?: number;

  constructor(message: string, status?: number) {
    super(message);
    this.name = "ApiError";
    this.status = status;
  }
}

type ApiFetchOptions = RequestInit & { timeoutMs?: number };

function requestSignal(options?: ApiFetchOptions): AbortSignal {
  const timeoutMs = options?.timeoutMs ?? Number(process.env.API_FETCH_TIMEOUT_MS ?? DEFAULT_TIMEOUT_MS);
  const timeoutSignal = AbortSignal.timeout(timeoutMs);
  if (options?.signal) {
    return AbortSignal.any([options.signal, timeoutSignal]);
  }
  return timeoutSignal;
}

export async function apiFetch<T>(
  path: string,
  accessToken?: string,
  options?: ApiFetchOptions,
): Promise<T> {
  const url = `${getApiUrl()}${path}`;
  const useBff = usesBffProxy();
  const port = apiPortLabel();

  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    ...(options?.headers as Record<string, string> | undefined),
  };

  if (!useBff) {
    if (!accessToken) {
      throw new ApiError("Not signed in", 401);
    }
    headers.Authorization = `Bearer ${accessToken}`;
  }

  let response: Response;
  try {
    response = await fetch(url, {
      ...options,
      cache: "no-store",
      credentials: useBff ? "include" : "same-origin",
      headers,
      signal: requestSignal(options),
    });
  } catch (err) {
    const msg = err instanceof Error ? err.message : "Network error";
    if (msg.includes("timeout") || msg.includes("aborted") || err instanceof DOMException) {
      throw new ApiError(
        `API request timed out — is the backend running on port ${port}? ${API_START_HINT}`,
        0,
      );
    }
    throw new ApiError(`Cannot reach API — ${API_START_HINT}`, 0);
  }

  if (!response.ok) {
    const raw = await response.text().catch(() => "");
    let detail = `API error ${response.status}`;
    if (raw) {
      try {
        const body = JSON.parse(raw) as { detail?: unknown };
        if (body.detail != null) {
          detail = typeof body.detail === "string" ? body.detail : JSON.stringify(body.detail);
        } else if (!raw.trimStart().startsWith("{")) {
          detail = raw.slice(0, 200);
        }
      } catch {
        detail = raw.slice(0, 200) || detail;
      }
    }
    throw new ApiError(detail, response.status);
  }

  return response.json() as Promise<T>;
}
