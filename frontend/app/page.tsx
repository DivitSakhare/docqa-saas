import Link from "next/link";
import { FileText, MessageSquareText, ShieldCheck } from "lucide-react";

import { LandingNav } from "@/components/marketing/landing-nav";
import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";

const FEATURES = [
  {
    icon: FileText,
    title: "Upload your documents",
    description:
      "Drop in a PDF or Word doc and it's parsed, chunked, and embedded in the background — you keep working while it processes.",
  },
  {
    icon: MessageSquareText,
    title: "Ask questions, get citations",
    description:
      "Every answer is grounded in your own documents and cites the exact document and page it came from — never a guess.",
  },
  {
    icon: ShieldCheck,
    title: "Built for multi-tenant isolation",
    description:
      "Each organization's documents and conversations are walled off at the database level, not just filtered in application code.",
  },
];

export default function LandingPage() {
  return (
    <div className="flex flex-1 flex-col">
      <LandingNav />

      {/* overflow-hidden is scoped to <main>, not the nav's own sticky
          container above — an overflow-hidden ancestor is a classic way to
          silently break position:sticky. */}
      <main className="relative flex flex-1 flex-col items-center justify-center overflow-hidden px-4 py-16 text-center lg:px-8">
        {/* Ambient glow — reuses existing theme tokens (primary/foreground)
            at low opacity rather than introducing new colors, so it stays
            correct in both light and dark without any palette changes. */}
        <div
          aria-hidden
          className="bg-primary/10 pointer-events-none absolute -top-40 left-1/2 -z-10 h-[32rem] w-[32rem] -translate-x-1/2 rounded-full blur-3xl"
        />
        <div
          aria-hidden
          className="bg-foreground/5 pointer-events-none absolute top-20 right-0 -z-10 h-96 w-96 rounded-full blur-3xl"
        />
        <h1 className="max-w-2xl text-4xl font-semibold tracking-tight text-balance lg:text-5xl">
          Ask your documents anything. Get answers you can actually check.
        </h1>
        <p className="text-muted-foreground mt-4 max-w-xl text-lg text-balance">
          Upload your team&apos;s PDFs and Word docs and chat with them in plain English — every
          answer cites the exact document and page it came from.
        </p>
        <div className="mt-8 flex gap-3">
          <Button size="lg" asChild>
            <Link href="/signup">Get started — it&apos;s free</Link>
          </Button>
          <Button size="lg" variant="outline" asChild>
            <Link href="/login">Log in</Link>
          </Button>
        </div>

        <div className="mt-20 grid w-full max-w-4xl gap-4 text-left sm:grid-cols-3">
          {FEATURES.map((feature) => (
            <Card
              key={feature.title}
              className="border-border/60 bg-card/60 shadow-none backdrop-blur-sm transition-shadow hover:shadow-lg hover:shadow-primary/5"
            >
              <CardContent className="space-y-2 pt-2">
                <feature.icon className="text-primary size-5" />
                <p className="font-medium">{feature.title}</p>
                <p className="text-muted-foreground text-sm">{feature.description}</p>
              </CardContent>
            </Card>
          ))}
        </div>
      </main>

      <footer className="text-muted-foreground px-4 py-6 text-center text-sm lg:px-8">
        Built as a demonstration of multi-tenant SaaS architecture — schema-per-tenant isolation,
        RAG with citations, and event-driven ingestion.
      </footer>
    </div>
  );
}
