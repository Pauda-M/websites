# ADR-0004: Frontend stack

## Status

Accepted — 2026-07-13

## Context

`apps/web` renders the public PB Solutions consulting site today and is the seed
for authenticated product surfaces later. It needs first-class server-side
rendering (SEO for the marketing site, server-side data fetching that never
leaks internal URLs to the browser), a design system the repository owns, strict
typing, and a minimal, self-contained production image that fits the Docker
Compose stack behind Traefik.

## Decision

We build the web app on **Next.js 15 (App Router)** with **TypeScript**:

- **Server components by default** (`apps/web/src/app/`); `"use client"` is added
  only where interaction demands it. The `/status` page
  (`app/status/page.tsx`) is the canonical data path: a server component calls
  the API through `@pb/api-client` and renders explicit
  operational / degraded / unreachable states, so the page never 500s because a
  dependency is down (`export const dynamic = "force-dynamic"`).
- **Tailwind CSS v4** for styling (`@tailwindcss/postcss`, CSS variables in
  `globals.css`, dark mode via the `.dark` class).
- **Vendored shadcn/ui primitives** under `src/components/ui/` — the components
  are copied into the repo (built on Radix + `class-variance-authority`), so the
  design system is owned here rather than pulled from an external component
  dependency.
- **`output: "standalone"`** in `next.config.ts` to produce a minimal
  self-contained server bundle for the Docker image, plus
  `transpilePackages: ["@pb/api-client"]` so the workspace client is compiled in.
- **`@pb/api-client`** (`packages/api-client`) as the only way the web app talks
  to the API — a typed client kept in lockstep with `shared/openapi/openapi.json`
  and covered by unit tests. Components never hand-roll `fetch`.
- **Environment access is centralised** in `src/lib/env.ts`: `API_INTERNAL_URL`
  (from `PB_WEB_API_INTERNAL_URL`) for server-side calls over the private
  network, and `NEXT_PUBLIC_API_URL` for the browser. Components never read
  `process.env` directly.

Quality gates are ESLint, `tsc --noEmit`, and Vitest + Testing Library
(colocated `*.test.tsx`); Prettier formats the TS tree.

## Alternatives Considered

- **Vite SPA (client-only React).** Fast dev and a simple mental model, but no
  server rendering — poor SEO for a marketing site, and every API call would go
  from the browser, forcing internal URLs and credentials client-side. Rejected:
  server components and server-side data fetching are core requirements.
- **Remix.** Strong server-first data loading and comparable to Next here, but
  the App Router gives the same benefits with the larger ecosystem and the
  streaming/server-component model the team standardised on. Rejected as a
  near-tie without a decisive advantage.
- **Plain React (CRA-style) or a hand-rolled SSR setup.** Maximum control, but
  reinvents routing, bundling, SSR, and image/asset handling that Next provides
  out of the box. Rejected as unjustified cost.

## Consequences

- Internal service URLs stay on the server: browser calls use
  `NEXT_PUBLIC_API_URL` (through Traefik), server calls use the internal URL, and
  the two never cross.
- `NEXT_PUBLIC_*` values are **inlined at build time**, so the browser bundle is
  built with the real public API URL as a Docker `build.arg`
  (`NEXT_PUBLIC_API_URL` in `docker-compose.yml`), not injected at runtime.
  Changing the browser-facing API URL requires a rebuild (see
  `docs/TROUBLESHOOTING.md`).
- Owning the shadcn/ui components means updates are deliberate (copy/patch),
  trading auto-updates for full control of the design system.
- The typed client is a single choke point for the web↔API contract; the e2e
  suite boots the real API and web build, so a contract break fails the local
  e2e run.
- The `standalone` output keeps the production image small and dependency-light.

## Future Considerations

- Additional deployable frontends (e.g. `apps/portal`) reusing `@pb/api-client`
  and a promoted `packages/ui`, as anticipated in `docs/ARCHITECTURE.md`.
- Authenticated, interactive surfaces will introduce more client components and
  client-side token handling; the current server-first default keeps that
  contained.
- Promote shared UI primitives from `apps/web` into a `packages/ui` workspace
  when the second consumer appears.
