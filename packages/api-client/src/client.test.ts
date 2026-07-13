import { describe, expect, it } from "vitest";

import { ApiError, PbApiClient } from "./client";

interface RecordedRequest {
  url: string;
  method: string;
  headers: Record<string, string>;
  body: string | null;
}

function stubFetch(responses: Array<{ status: number; body: unknown }>) {
  const requests: RecordedRequest[] = [];
  let call = 0;
  const fetchImpl = (async (input: URL | string, init?: RequestInit) => {
    const spec = responses[Math.min(call, responses.length - 1)];
    if (!spec) throw new Error("stubFetch: no response configured");
    call += 1;
    requests.push({
      url: input instanceof URL ? input.toString() : String(input),
      method: init?.method ?? "GET",
      headers: (init?.headers as Record<string, string>) ?? {},
      body: typeof init?.body === "string" ? init.body : null,
    });
    return new Response(JSON.stringify(spec.body), {
      status: spec.status,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  return { fetchImpl, requests };
}

describe("PbApiClient", () => {
  it("performs liveness checks against the versioned health route", async () => {
    const { fetchImpl, requests } = stubFetch([
      {
        status: 200,
        body: { status: "ok", service: "pb-api", version: "0.1.0", environment: "test" },
      },
    ]);
    const client = new PbApiClient({ baseUrl: "http://api:8000/", fetch: fetchImpl });

    const live = await client.health.live();

    expect(live.service).toBe("pb-api");
    expect(requests[0]?.url).toBe("http://api:8000/api/v1/health/live");
  });

  it("treats readiness 503 as a valid degraded response", async () => {
    const { fetchImpl } = stubFetch([
      { status: 503, body: { status: "degraded", checks: { database: "error", redis: "ok" } } },
    ]);
    const client = new PbApiClient({ baseUrl: "http://api:8000", fetch: fetchImpl });

    const ready = await client.health.ready();

    expect(ready.status).toBe("degraded");
    expect(ready.checks.database).toBe("error");
  });

  it("sends JSON bodies and parses token pairs on login", async () => {
    const { fetchImpl, requests } = stubFetch([
      {
        status: 200,
        body: { access_token: "a", refresh_token: "r", token_type: "bearer", expires_in: 900 },
      },
    ]);
    const client = new PbApiClient({ baseUrl: "http://api:8000", fetch: fetchImpl });

    const tokens = await client.auth.login({ email: "a@b.co", password: "pw-pw-pw-pw" });

    expect(tokens.access_token).toBe("a");
    expect(requests[0]?.method).toBe("POST");
    expect(requests[0]?.headers["Content-Type"]).toBe("application/json");
    expect(JSON.parse(requests[0]?.body ?? "{}")).toEqual({
      email: "a@b.co",
      password: "pw-pw-pw-pw",
    });
  });

  it("attaches bearer tokens to authenticated requests", async () => {
    const { fetchImpl, requests } = stubFetch([
      {
        status: 200,
        body: {
          id: "1",
          email: "a@b.co",
          full_name: "A",
          role: "client",
          is_active: true,
          created_at: "2026-01-01T00:00:00Z",
        },
      },
    ]);
    const client = new PbApiClient({
      baseUrl: "http://api:8000",
      fetch: fetchImpl,
      accessToken: () => "token-123",
    });

    await client.users.me();

    expect(requests[0]?.headers.Authorization).toBe("Bearer token-123");
  });

  it("throws ApiError with the API's detail message on failures", async () => {
    const { fetchImpl } = stubFetch([
      { status: 401, body: { detail: "Incorrect email or password" } },
    ]);
    const client = new PbApiClient({ baseUrl: "http://api:8000", fetch: fetchImpl });

    const error = await client.auth
      .login({ email: "a@b.co", password: "wrong" })
      .catch((e: unknown) => e);

    expect(error).toBeInstanceOf(ApiError);
    expect((error as ApiError).status).toBe(401);
    expect((error as ApiError).message).toBe("Incorrect email or password");
  });

  it("refuses authenticated calls without a token", async () => {
    const { fetchImpl, requests } = stubFetch([{ status: 200, body: {} }]);
    const client = new PbApiClient({ baseUrl: "http://api:8000", fetch: fetchImpl });

    await expect(client.users.me()).rejects.toThrow(ApiError);
    expect(requests).toHaveLength(0);
  });

  it("serialises pagination query parameters", async () => {
    const { fetchImpl, requests } = stubFetch([
      { status: 200, body: { items: [], total: 0, limit: 10, offset: 20 } },
    ]);
    const client = new PbApiClient({
      baseUrl: "http://api:8000",
      fetch: fetchImpl,
      accessToken: "t",
    });

    await client.users.list({ limit: 10, offset: 20 });

    expect(requests[0]?.url).toBe("http://api:8000/api/v1/users?limit=10&offset=20");
  });
});
