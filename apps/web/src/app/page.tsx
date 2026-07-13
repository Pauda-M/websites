import Link from "next/link";
import { ArrowRight, Bot, Handshake, LifeBuoy, Users } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";

const services = [
  {
    title: "Consulting",
    icon: Handshake,
    description:
      "Hands-on technology and process consulting, from architecture reviews to delivery leadership. We work inside your team until the outcome ships.",
  },
  {
    title: "CRM & Client Portal",
    icon: Users,
    description:
      "A single view of every client relationship, paired with a secure portal where your customers track projects, documents, and invoices.",
  },
  {
    title: "AI Services",
    icon: Bot,
    description:
      "Practical AI integrations — assistants, document automation, and analytics — built on your data and deployed inside your own infrastructure.",
  },
  {
    title: "Support & Ticketing",
    icon: LifeBuoy,
    description:
      "Structured intake, SLAs, and transparent ticket tracking so nothing falls through the cracks after go-live.",
  },
];

const platformPillars = [
  {
    name: "One data model",
    detail: "Clients, projects, tickets, and billing share a single source of truth.",
  },
  {
    name: "API-first",
    detail: "Everything the platform does is available through a versioned REST API.",
  },
  {
    name: "Self-hosted",
    detail: "Runs on your infrastructure with observability and health checks built in.",
  },
];

export default function Home() {
  return (
    <div className="flex min-h-screen flex-col">
      <header className="sticky top-0 z-50 border-b border-border/60 bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="mx-auto flex h-14 w-full max-w-6xl items-center justify-between px-4 sm:px-6">
          <Link href="/" className="text-base font-semibold tracking-tight">
            PB&nbsp;Solutions
          </Link>
          <nav aria-label="Main" className="flex items-center gap-1 sm:gap-2">
            <Button variant="ghost" size="sm" asChild>
              <Link href="#services">Services</Link>
            </Button>
            <Button variant="ghost" size="sm" asChild>
              <Link href="#platform">Platform</Link>
            </Button>
            <Button variant="ghost" size="sm" asChild>
              <Link href="/status">Status</Link>
            </Button>
          </nav>
        </div>
      </header>

      <main className="flex-1">
        <section className="mx-auto w-full max-w-6xl px-4 py-20 sm:px-6 sm:py-28">
          <div className="max-w-3xl">
            <Badge variant="secondary" className="mb-4">
              Consulting &middot; Software &middot; Support
            </Badge>
            <h1 className="text-4xl font-semibold tracking-tight text-balance sm:text-5xl lg:text-6xl">
              Consulting and software, engineered for outcomes.
            </h1>
            <p className="mt-6 max-w-2xl text-lg text-muted-foreground">
              PB Solutions combines senior consulting with the PB Platform — our own CRM, client
              portal, AI services, and support tooling — so strategy and execution live in the same
              place.
            </p>
            <div className="mt-8 flex flex-wrap items-center gap-3">
              <Button size="lg" asChild>
                <Link href="#services">
                  Explore services
                  <ArrowRight aria-hidden="true" />
                </Link>
              </Button>
              <Button size="lg" variant="outline" asChild>
                <Link href="/status">Platform status</Link>
              </Button>
            </div>
          </div>
        </section>

        <section id="services" className="border-t border-border/60 bg-muted/30">
          <div className="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
            <div className="mb-10 max-w-2xl">
              <h2 className="text-3xl font-semibold tracking-tight">Services</h2>
              <p className="mt-3 text-muted-foreground">
                Four practices, one team. Every engagement is backed by the PB Platform from day
                one.
              </p>
            </div>
            <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
              {services.map((service) => (
                <Card key={service.title} className="gap-4">
                  <CardHeader>
                    <div className="mb-2 flex size-10 items-center justify-center rounded-lg bg-primary/10 text-primary">
                      <service.icon className="size-5" aria-hidden="true" />
                    </div>
                    <CardTitle>
                      <h3>{service.title}</h3>
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <CardDescription className="text-sm leading-relaxed">
                      {service.description}
                    </CardDescription>
                  </CardContent>
                </Card>
              ))}
            </div>
          </div>
        </section>

        <section id="platform" className="border-t border-border/60">
          <div className="mx-auto w-full max-w-6xl px-4 py-16 sm:px-6 sm:py-20">
            <div className="grid items-start gap-10 lg:grid-cols-2">
              <div className="max-w-xl">
                <h2 className="text-3xl font-semibold tracking-tight">The PB Platform</h2>
                <p className="mt-4 text-muted-foreground">
                  The PB Platform is the operating system behind every engagement: a self-hosted
                  suite covering CRM, client portal, AI services, and ticketing, exposed through a
                  documented API and monitored end to end.
                </p>
                <div className="mt-6">
                  <Button variant="outline" asChild>
                    <Link href="/status">
                      Check live status
                      <ArrowRight aria-hidden="true" />
                    </Link>
                  </Button>
                </div>
              </div>
              <dl className="grid gap-4">
                {platformPillars.map((pillar) => (
                  <div key={pillar.name} className="rounded-xl border border-border/60 p-5">
                    <dt className="font-medium">{pillar.name}</dt>
                    <dd className="mt-1 text-sm text-muted-foreground">{pillar.detail}</dd>
                  </div>
                ))}
              </dl>
            </div>
          </div>
        </section>
      </main>

      <footer className="border-t border-border/60">
        <div className="mx-auto flex w-full max-w-6xl flex-col items-center justify-between gap-2 px-4 py-8 text-sm text-muted-foreground sm:flex-row sm:px-6">
          <p>&copy; 2026 PB Solutions. All rights reserved.</p>
          <p>Built on the PB Platform.</p>
        </div>
      </footer>
    </div>
  );
}
