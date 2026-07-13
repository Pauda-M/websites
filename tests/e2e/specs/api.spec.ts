import { expect, test } from "@playwright/test";

import { API_URL } from "../playwright.config";

const password = "an-e2e-passphrase-42";

function uniqueEmail(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.floor(Math.random() * 1e6)}@example.com`;
}

test.describe("API over real HTTP", () => {
  test("liveness and readiness respond", async ({ request }) => {
    const live = await request.get(`${API_URL}/api/v1/health/live`);
    expect(live.status()).toBe(200);
    expect((await live.json()).service).toBe("pb-api");

    const ready = await request.get(`${API_URL}/api/v1/health/ready`);
    expect(ready.status()).toBe(200);
    expect((await ready.json()).checks.database).toBe("ok");
  });

  test("register -> login -> me round-trip", async ({ request }) => {
    const email = uniqueEmail("roundtrip");

    const register = await request.post(`${API_URL}/api/v1/auth/register`, {
      data: { email, password, full_name: "E2E User" },
    });
    expect(register.status()).toBe(201);
    expect((await register.json()).role).toBe("client");

    const login = await request.post(`${API_URL}/api/v1/auth/login`, {
      data: { email, password },
    });
    expect(login.status()).toBe(200);
    const tokens = await login.json();
    expect(tokens.token_type).toBe("bearer");

    const me = await request.get(`${API_URL}/api/v1/users/me`, {
      headers: { Authorization: `Bearer ${tokens.access_token}` },
    });
    expect(me.status()).toBe(200);
    expect((await me.json()).email).toBe(email);
  });

  test("wrong credentials are rejected", async ({ request }) => {
    const email = uniqueEmail("badcreds");
    await request.post(`${API_URL}/api/v1/auth/register`, {
      data: { email, password, full_name: "E2E User" },
    });

    const login = await request.post(`${API_URL}/api/v1/auth/login`, {
      data: { email, password: "wrong-password-xyz" },
    });
    expect(login.status()).toBe(401);
  });

  test("client role cannot access the admin user list", async ({ request }) => {
    const email = uniqueEmail("rbac");
    await request.post(`${API_URL}/api/v1/auth/register`, {
      data: { email, password, full_name: "E2E User" },
    });
    const login = await request.post(`${API_URL}/api/v1/auth/login`, {
      data: { email, password },
    });
    const tokens = await login.json();

    const list = await request.get(`${API_URL}/api/v1/users`, {
      headers: { Authorization: `Bearer ${tokens.access_token}` },
    });
    expect(list.status()).toBe(403);
  });

  test("security headers are set on API responses", async ({ request }) => {
    const response = await request.get(`${API_URL}/api/v1/health/live`);
    const headers = response.headers();
    expect(headers["x-content-type-options"]).toBe("nosniff");
    expect(headers["x-frame-options"]).toBe("DENY");
    expect(headers["x-request-id"]).toBeTruthy();
  });
});
