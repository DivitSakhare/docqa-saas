"use client";

import { useState } from "react";
import { MutationCache, QueryCache, QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { ThemeProvider } from "next-themes";
import { Toaster } from "@/components/ui/sonner";
import { ClientApiError } from "@/lib/api";

// A 401 from any protected query/mutation means the session is dead (the
// BFF already tried one refresh server-side and it still failed) — send
// the user to /login. Auth mutations themselves (login/signup) opt out via
// `meta.skipAuthRedirect`, since a wrong password is an expected 401 that
// should surface as a form error, not a redirect.
function isUnauthorized(error: unknown) {
  return error instanceof ClientApiError && error.status === 401;
}

function redirectToLogin() {
  // A full navigation, deliberately: this fires from the QueryClient's
  // global error handlers, outside any component's render or event
  // context, so `useRouter()` isn't reachable here — and a hard reload
  // usefully drops all client-side query cache along with the dead
  // session.
  if (typeof window !== "undefined") {
    // eslint-disable-next-line @next/next/no-location-assign-relative-destination
    window.location.href = "/login";
  }
}

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, staleTime: 30_000 },
    },
    queryCache: new QueryCache({
      onError: (error, query) => {
        if (isUnauthorized(error) && !query.meta?.skipAuthRedirect) {
          redirectToLogin();
        }
      },
    }),
    mutationCache: new MutationCache({
      onError: (error, _variables, _context, mutation) => {
        if (isUnauthorized(error) && !mutation.meta?.skipAuthRedirect) {
          redirectToLogin();
        }
      },
    }),
  });
}

export function Providers({ children }: { children: React.ReactNode }) {
  const [queryClient] = useState(createQueryClient);

  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider attribute="class" defaultTheme="system" enableSystem disableTransitionOnChange>
        {children}
        <Toaster />
      </ThemeProvider>
    </QueryClientProvider>
  );
}
