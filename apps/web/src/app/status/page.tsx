import type { Metadata } from "next";
import Link from "next/link";
import { Activity, AlertTriangle, ArrowLeft, CheckCircle2, XCircle } from "lucide-react";

import { PbApiClient } from "@pb/api-client";
import type { LivenessResponse, ReadinessResponse } from "@pb/api-client";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { env } from "@/lib/env";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "Platform Status | PB Solutions",
  description: "Live health of the PB Platform API and its dependencies.",
};

interface HealthResult<T> {
  reachable: boolean;
  data?: T;
}

async function safeCheck<T>(check: () => Promise<T>): Promise<HealthResult<T>> {
  try {
    return { reachable: true, data: await check() };
  } catch {
    // Network failure, timeout, or malformed response — the page must render
    // an "unreachable" state instead of failing.
    return { reachable: false };
  }
}

function StatusBadge({ status }: { status: string }) {
  if (status === "ok") {
    return (
      <Badge className="bg-emerald-600 text-white dark:bg-emerald-500 dark:text-emerald-950">
        <CheckCircle2 aria-hidden="true" />
        Operational
      </Badge>
    );
  }
  if (status === "degraded") {
    return (
      <Badge className="bg-amber-500 text-amber-950">
        <AlertTriangle aria-hidden="true" />
        Degraded
      </Badge>
    );
  }
  return (
    <Badge variant="destructive" className="capitalize">
      <XCircle aria-hidden="true" />
      {status}
    </Badge>
  );
}

export default async function StatusPage() {
  const api = new PbApiClient({ baseUrl: env.API_INTERNAL_URL, timeoutMs: 3000 });
  const [live, ready] = await Promise.all([
    safeCheck<LivenessResponse>(() => api.health.live()),
    safeCheck<ReadinessResponse>(() => api.health.ready()),
  ]);

  const apiReachable = live.reachable || ready.reachable;
  const liveStatus = live.reachable ? (live.data?.status ?? "unknown") : "unreachable";
  const readyStatus = ready.reachable ? (ready.data?.status ?? "unknown") : "unreachable";
  const checks = ready.data?.checks ?? {};
  const checkEntries = Object.entries(checks);

  const overall = !apiReachable
    ? "unreachable"
    : liveStatus === "ok" && readyStatus === "ok"
      ? "ok"
      : "degraded";

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-border/60">
        <div className="mx-auto flex h-14 w-full max-w-4xl items-center justify-between px-4 sm:px-6">
          <Link href="/" className="text-base font-semibold tracking-tight">
            PB&nbsp;Solutions
          </Link>
          <Button variant="ghost" size="sm" asChild>
            <Link href="/">
              <ArrowLeft aria-hidden="true" />
              Back to home
            </Link>
          </Button>
        </div>
      </header>

      <main className="mx-auto w-full max-w-4xl flex-1 px-4 py-12 sm:px-6">
        <div className="mb-8 flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="flex items-center gap-2 text-3xl font-semibold tracking-tight">
              <Activity className="size-7" aria-hidden="true" />
              Platform Status
            </h1>
            <p className="mt-2 text-muted-foreground">
              Live health of the PB Platform API and its dependencies.
            </p>
          </div>
          <StatusBadge status={overall} />
        </div>

        {!apiReachable && (
          <Card className="mb-6 border-destructive/50">
            <CardHeader>
              <CardTitle className="flex items-center gap-2">
                <XCircle className="size-5 text-destructive" aria-hidden="true" />
                API unreachable
              </CardTitle>
              <CardDescription>
                The PB API did not respond within 3 seconds. It may be down, restarting, or not
                reachable from this environment. Refresh this page to retry.
              </CardDescription>
            </CardHeader>
          </Card>
        )}

        <div className="grid gap-4 sm:grid-cols-2">
          <Card>
            <CardHeader>
              <CardTitle>
                <h2>Liveness</h2>
              </CardTitle>
              <CardDescription>GET /api/v1/health/live</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <StatusBadge status={liveStatus} />
              {live.reachable && (
                <dl className="grid gap-1 text-sm text-muted-foreground">
                  <div className="flex justify-between gap-4">
                    <dt>Service</dt>
                    <dd className="font-mono">{live.data?.service ?? "unknown"}</dd>
                  </div>
                  <div className="flex justify-between gap-4">
                    <dt>Version</dt>
                    <dd className="font-mono">{live.data?.version ?? "unknown"}</dd>
                  </div>
                  <div className="flex justify-between gap-4">
                    <dt>Environment</dt>
                    <dd className="font-mono">{live.data?.environment ?? "unknown"}</dd>
                  </div>
                </dl>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>
                <h2>Readiness</h2>
              </CardTitle>
              <CardDescription>GET /api/v1/health/ready</CardDescription>
            </CardHeader>
            <CardContent className="flex flex-col gap-3">
              <StatusBadge status={readyStatus} />
              {ready.reachable && checkEntries.length > 0 && (
                <ul className="grid gap-2 text-sm">
                  {checkEntries.map(([name, value]) => (
                    <li
                      key={name}
                      className="flex items-center justify-between gap-4 rounded-md border border-border/60 px-3 py-2"
                    >
                      <span className="font-mono capitalize">{name}</span>
                      <StatusBadge status={value} />
                    </li>
                  ))}
                </ul>
              )}
              {ready.reachable && checkEntries.length === 0 && (
                <p className="text-sm text-muted-foreground">No dependency checks reported.</p>
              )}
            </CardContent>
          </Card>
        </div>

        <p className="mt-8 text-sm text-muted-foreground">
          Checked live on every request. Data is never cached.
        </p>
      </main>

      <footer className="border-t border-border/60">
        <div className="mx-auto w-full max-w-4xl px-4 py-8 text-sm text-muted-foreground sm:px-6">
          <p>&copy; 2026 PB Solutions. All rights reserved.</p>
        </div>
      </footer>
    </div>
  );
}
