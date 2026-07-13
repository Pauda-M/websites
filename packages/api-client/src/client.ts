import type {
  LivenessResponse,
  LoginInput,
  ReadinessResponse,
  RegisterInput,
  TokenPair,
  User,
  UserList,
} from "./types";

export interface PbApiClientOptions {
  /** Base URL of the API service, e.g. "http://api:8000" or "https://api.pbsolutions.example". */
  baseUrl: string;
  /** Bearer token (or provider) attached to authenticated requests. */
  accessToken?: string | (() => string | null | undefined);
  /** Custom fetch implementation (tests, polyfills). Defaults to globalThis.fetch. */
  fetch?: typeof fetch;
  /** Per-request timeout in milliseconds. Defaults to 10 000. */
  timeoutMs?: number;
}

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : `API request failed with status ${status}`);
    this.name = "ApiError";
    this.status = status;
    this.detail = detail;
  }
}

interface RequestOptions {
  method: "GET" | "POST" | "PUT" | "PATCH" | "DELETE";
  path: string;
  body?: unknown;
  auth?: boolean;
  query?: Record<string, string | number | undefined>;
  /** HTTP statuses (besides 2xx) whose JSON body is a valid, expected response. */
  acceptStatuses?: number[];
}

export class PbApiClient {
  private readonly baseUrl: string;
  private readonly options: PbApiClientOptions;

  constructor(options: PbApiClientOptions) {
    this.baseUrl = options.baseUrl.replace(/\/+$/, "");
    this.options = options;
  }

  private resolveToken(): string | null {
    const { accessToken } = this.options;
    if (typeof accessToken === "function") return accessToken() ?? null;
    return accessToken ?? null;
  }

  private async request<T>(options: RequestOptions): Promise<T> {
    const url = new URL(this.baseUrl + options.path);
    for (const [key, value] of Object.entries(options.query ?? {})) {
      if (value !== undefined) url.searchParams.set(key, String(value));
    }

    const headers: Record<string, string> = { Accept: "application/json" };
    if (options.body !== undefined) headers["Content-Type"] = "application/json";
    if (options.auth) {
      const token = this.resolveToken();
      if (!token) {
        throw new ApiError(401, "No access token configured for an authenticated request");
      }
      headers.Authorization = `Bearer ${token}`;
    }

    const doFetch = this.options.fetch ?? globalThis.fetch;
    const response = await doFetch(url, {
      method: options.method,
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: AbortSignal.timeout(this.options.timeoutMs ?? 10_000),
    });

    const accepted = response.ok || (options.acceptStatuses ?? []).includes(response.status);
    if (!accepted) {
      let detail: unknown = null;
      try {
        const parsed = (await response.json()) as { detail?: unknown };
        detail = parsed.detail ?? parsed;
      } catch {
        detail = response.statusText;
      }
      throw new ApiError(response.status, detail);
    }
    return (await response.json()) as T;
  }

  readonly health = {
    live: (): Promise<LivenessResponse> =>
      this.request({ method: "GET", path: "/api/v1/health/live" }),
    ready: (): Promise<ReadinessResponse> =>
      this.request({
        method: "GET",
        path: "/api/v1/health/ready",
        // 503 carries the same shape with per-dependency detail.
        acceptStatuses: [503],
      }),
  };

  readonly auth = {
    register: (input: RegisterInput): Promise<User> =>
      this.request({ method: "POST", path: "/api/v1/auth/register", body: input }),
    login: (input: LoginInput): Promise<TokenPair> =>
      this.request({ method: "POST", path: "/api/v1/auth/login", body: input }),
    refresh: (refreshToken: string): Promise<TokenPair> =>
      this.request({
        method: "POST",
        path: "/api/v1/auth/refresh",
        body: { refresh_token: refreshToken },
      }),
  };

  readonly users = {
    me: (): Promise<User> => this.request({ method: "GET", path: "/api/v1/users/me", auth: true }),
    list: (params?: { limit?: number; offset?: number }): Promise<UserList> =>
      this.request({
        method: "GET",
        path: "/api/v1/users",
        auth: true,
        query: { limit: params?.limit, offset: params?.offset },
      }),
  };
}
