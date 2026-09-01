"use client";

import { useState } from "react";
import { useRouter } from "next/navigation";
import { LogOut, Menu, ShieldOff } from "lucide-react";
import { toast } from "sonner";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from "@/components/ui/dropdown-menu";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { SidebarNav } from "@/components/layout/sidebar-nav";
import { ThemeToggle } from "@/components/layout/theme-toggle";
import { useLogout, useLogoutAll } from "@/hooks/use-auth-actions";
import { useCurrentUser } from "@/hooks/use-current-user";

export function Topbar() {
  const router = useRouter();
  const { data: user } = useCurrentUser();
  const logout = useLogout();
  const logoutAll = useLogoutAll();
  const [sheetOpen, setSheetOpen] = useState(false);

  async function handleLogout() {
    await logout.mutateAsync().catch(() => undefined);
    router.push("/login");
  }

  async function handleLogoutAll() {
    await logoutAll.mutateAsync().catch(() => undefined);
    toast.info("Logged out of every device.");
    router.push("/login");
  }

  const initial = user?.email?.[0]?.toUpperCase() ?? "?";

  return (
    <header className="grid h-14 grid-cols-[auto_1fr_auto] items-center gap-2 border-b px-4 lg:px-6">
      <div className="flex items-center gap-2">
        <Sheet open={sheetOpen} onOpenChange={setSheetOpen}>
          <SheetTrigger asChild>
            <Button variant="ghost" size="icon" className="lg:hidden" aria-label="Open navigation">
              <Menu className="size-5" />
            </Button>
          </SheetTrigger>
          <SheetContent side="left" className="w-64 p-0">
            <SheetHeader className="border-b px-4 py-3">
              <SheetTitle className="text-base">DocQA</SheetTitle>
            </SheetHeader>
            <SidebarNav onNavigate={() => setSheetOpen(false)} />
          </SheetContent>
        </Sheet>
      </div>

      <span className="justify-self-center text-xl font-semibold tracking-tight lg:hidden">DocQA</span>

      <div className="flex items-center justify-self-end gap-2">
        <ThemeToggle />
        <DropdownMenu>
          <DropdownMenuTrigger asChild>
            <Button variant="ghost" className="gap-2 px-2">
              <Avatar className="size-6">
                <AvatarFallback className="text-xs">{initial}</AvatarFallback>
              </Avatar>
              <span className="hidden text-sm sm:inline">{user?.email}</span>
            </Button>
          </DropdownMenuTrigger>
          <DropdownMenuContent align="end" className="w-64">
            <DropdownMenuLabel className="font-normal">
              <p className="text-sm font-medium">{user?.email}</p>
              <p className="text-muted-foreground text-xs capitalize">{user?.role}</p>
            </DropdownMenuLabel>
            <DropdownMenuSeparator />
            <DropdownMenuItem onSelect={handleLogout}>
              <LogOut />
              Log out
            </DropdownMenuItem>
            <DropdownMenuItem variant="destructive" onSelect={handleLogoutAll}>
              <ShieldOff />
              Log out everywhere
            </DropdownMenuItem>
          </DropdownMenuContent>
        </DropdownMenu>
      </div>
    </header>
  );
}
