import type { ReactNode } from "react";

import { SidebarNav } from "@/components/layout/sidebar-nav";
import { Topbar } from "@/components/layout/topbar";

export function AppShell({ children }: { children: ReactNode }) {
  return (
    <div className="flex h-dvh flex-col">
      <Topbar />
      <div className="flex flex-1 overflow-hidden">
        <aside className="hidden w-56 shrink-0 border-r lg:block">
          <div className="border-b px-4 py-3 text-center">
            <span className="text-xl font-semibold tracking-tight">DocQA</span>
          </div>
          <SidebarNav />
        </aside>
        <main className="flex-1 overflow-y-auto">
          <div className="mx-auto h-full max-w-5xl px-4 py-6 lg:px-8">{children}</div>
        </main>
      </div>
    </div>
  );
}
