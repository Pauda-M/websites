/**
 * Typed environment access for the PB Platform web app.
 *
 * Values fall back to local-development defaults so that `next build`
 * and local tooling never throw when the variables are unset.
 */
export interface Env {
  /**
   * Base URL the server uses to reach the PB API inside the private network
   * (e.g. the Docker network). Server-side only — never expose to the client.
   */
  API_INTERNAL_URL: string;
  /**
   * Base URL the browser uses to reach the PB API. Inlined at build time
   * because of the NEXT_PUBLIC_ prefix.
   */
  NEXT_PUBLIC_API_URL: string;
}

export const env: Env = {
  API_INTERNAL_URL: process.env.PB_WEB_API_INTERNAL_URL ?? "http://localhost:8000",
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL ?? "http://localhost:8000",
};
