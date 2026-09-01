"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";

import { ThemeToggle } from "@/components/layout/theme-toggle";
import { Button } from "@/components/ui/button";
import { cn } from "@/lib/utils";

export function LandingNav() {
  const [scrolled, setScrolled] = useState(false);
  // A sentinel at the very top of the page rather than a `scroll` event
  // listener: IntersectionObserver reacts to real layout/viewport
  // position regardless of whether a `scroll` event happens to fire,
  // and is the standard way to implement this exact effect anyway
  // (no per-frame scroll handler needed).
  const sentinelRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const sentinel = sentinelRef.current;
    if (!sentinel) return;
    // No rootMargin here on purpose: a negative top margin shrinks the
    // *root* (viewport), not the sentinel — with a 1px sentinel sitting
    // exactly at y=0, that made it register as "not intersecting" even
    // at scrollY 0, so `scrolled` was true from first paint. Giving the
    // sentinel real height (below) is what actually creates the
    // threshold, without touching rootMargin at all.
    const observer = new IntersectionObserver(([entry]) => setScrolled(!entry.isIntersecting));
    observer.observe(sentinel);
    return () => observer.disconnect();
  }, []);

  return (
    <>
      {/* Pinned to the true top of the document (absolute, not sticky) so
          it never occupies layout space — the nav below still renders
          flush at its normal `pt-4` offset at rest. Its height (not
          rootMargin) is the scroll threshold: the header switches to its
          "scrolled" look once this has fully scrolled past the
          viewport's top edge. */}
      <div ref={sentinelRef} aria-hidden className="absolute top-0 h-6 w-px" />
      <div className="sticky top-0 z-50 flex justify-center px-4 pt-4">
        <header
          className={cn(
            "grid w-full grid-cols-[1fr_auto_1fr] items-center gap-4 rounded-full border border-transparent px-4 py-3 transition-all duration-300 ease-out",
            scrolled
              ? "max-w-2xl border-border/60 bg-background/70 px-5 py-2.5 shadow-lg shadow-black/5 backdrop-blur-md"
              : "max-w-6xl bg-transparent"
          )}
        >
          {/* Empty spacer — balances the grid so the logo in the middle
              column sits truly centered regardless of how wide the
              button group on the right ends up being. */}
          <span aria-hidden />
          <Link href="/" className="justify-self-center text-xl font-semibold tracking-tight">
            DocQA
          </Link>
          <div className="flex items-center justify-self-end gap-2">
            <ThemeToggle />
            <Button variant="ghost" size="sm" asChild>
              <Link href="/login">Log in</Link>
            </Button>
            <Button size="sm" asChild>
              <Link href="/signup">Sign up</Link>
            </Button>
          </div>
        </header>
      </div>
    </>
  );
}
