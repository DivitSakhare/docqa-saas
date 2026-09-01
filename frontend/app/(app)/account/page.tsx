"use client";

import { useRouter } from "next/navigation";
import { toast } from "sonner";

import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Separator } from "@/components/ui/separator";
import { useLogout, useLogoutAll } from "@/hooks/use-auth-actions";
import { useCurrentUser } from "@/hooks/use-current-user";

export default function AccountPage() {
  const router = useRouter();
  const { data: user, isLoading } = useCurrentUser();
  const logout = useLogout();
  const logoutAll = useLogoutAll();

  async function handleLogout() {
    await logout.mutateAsync().catch(() => undefined);
    router.push("/login");
  }

  async function handleLogoutAll() {
    await logoutAll.mutateAsync().catch(() => undefined);
    toast.info("Logged out of every device.");
    router.push("/login");
  }

  return (
    <div className="max-w-lg space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">Account</h1>
        <p className="text-muted-foreground text-sm">Your profile and session.</p>
      </div>

      <Card>
        <CardHeader className="flex-row items-center gap-4 space-y-0">
          <Avatar className="size-12">
            <AvatarFallback>{user?.email?.[0]?.toUpperCase() ?? "?"}</AvatarFallback>
          </Avatar>
          <div>
            <CardTitle className="text-base">{isLoading ? "Loading…" : user?.email}</CardTitle>
            <CardDescription className="capitalize">{user?.role}</CardDescription>
          </div>
        </CardHeader>
      </Card>

      <Card>
        <CardHeader>
          <CardTitle className="text-base">Session</CardTitle>
          <CardDescription>
            Sign out of this device, or every device you&apos;re logged into.
          </CardDescription>
        </CardHeader>
        <CardContent className="flex flex-col gap-3">
          <Button variant="outline" onClick={handleLogout} disabled={logout.isPending}>
            Log out
          </Button>
          <Separator />
          <div className="space-y-2">
            <Button variant="destructive" onClick={handleLogoutAll} disabled={logoutAll.isPending}>
              Log out of every device
            </Button>
            <p className="text-muted-foreground text-xs">
              Revokes every refresh token immediately. Any access token already issued elsewhere
              stays valid until it naturally expires (up to an hour) — see the project&apos;s Not
              Now notes on instant revocation.
            </p>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
