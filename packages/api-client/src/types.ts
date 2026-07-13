/**
 * Wire types for the PB Platform API (source of truth: shared/openapi/openapi.json,
 * exported from the FastAPI app). Keep field names in snake_case — they mirror
 * the JSON payloads exactly.
 */

export type UserRole = "admin" | "staff" | "client";

export interface User {
  id: string;
  email: string;
  full_name: string;
  role: UserRole;
  is_active: boolean;
  created_at: string;
}

export interface UserList {
  items: User[];
  total: number;
  limit: number;
  offset: number;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type: "bearer";
  expires_in: number;
}

export interface RegisterInput {
  email: string;
  password: string;
  full_name: string;
}

export interface LoginInput {
  email: string;
  password: string;
}

export type CheckStatus = "ok" | "error" | "skipped";

export interface LivenessResponse {
  status: "ok";
  service: string;
  version: string;
  environment: string;
}

export interface ReadinessResponse {
  status: "ok" | "degraded";
  checks: Record<string, CheckStatus>;
}
