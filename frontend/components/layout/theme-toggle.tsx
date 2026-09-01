"use client";

import { useEffect, useState } from "react";
import { Moon, Sun } from "lucide-react";
import { useTheme } from "next-themes";

import { Button } from "@/components/ui/button";

export function ThemeToggle() {
  const { resolvedTheme, setTheme } = useTheme();
  const [mounted, setMounted] = useState(false);

  // next-themes resolves the system theme synchronously on the client's
  // very first render (before hydration reconciliation), which differs
  // from the server's unresolved value — so checking `resolvedTheme`
  // directly still mismatches. A mounted flag, set after the first
  // commit, is next-themes' own documented fix; the mount-detection
  // effect below intentionally doesn't fit the "effects subscribe to
  // external systems" shape the linter otherwise expects.
  // eslint-disable-next-line react-hooks/set-state-in-effect
  useEffect(() => setMounted(true), []);

  const isDark = resolvedTheme === "dark";

  return (
    <Button
      variant="ghost"
      size="icon"
      aria-label="Toggle theme"
      onClick={() => setTheme(isDark ? "light" : "dark")}
    >
      {mounted ? isDark ? <Sun className="size-4" /> : <Moon className="size-4" /> : null}
    </Button>
  );
}
