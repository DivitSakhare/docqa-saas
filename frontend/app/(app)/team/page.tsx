"use client";

import { Users } from "lucide-react";

import { EmptyState } from "@/components/shared/empty-state";
import { AddMemberDialog } from "@/components/team/add-member-dialog";
import { Avatar, AvatarFallback } from "@/components/ui/avatar";
import { Badge } from "@/components/ui/badge";
import { Skeleton } from "@/components/ui/skeleton";
import { useCurrentUser } from "@/hooks/use-current-user";
import { useTeamMembers } from "@/hooks/use-team";

function formatDate(iso: string) {
  return new Date(iso).toLocaleDateString(undefined, { dateStyle: "medium" });
}

export default function TeamPage() {
  const { data: currentUser } = useCurrentUser();
  const { data: members, isLoading } = useTeamMembers();
  const isAdmin = currentUser?.role === "admin";

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">Team</h1>
          <p className="text-muted-foreground text-sm">Everyone with access to your workspace.</p>
        </div>
        {isAdmin && <AddMemberDialog />}
      </div>

      {isLoading ? (
        <div className="space-y-2">
          <Skeleton className="h-14 w-full" />
          <Skeleton className="h-14 w-full" />
        </div>
      ) : !members || members.length === 0 ? (
        <EmptyState
          icon={<Users className="size-8" />}
          title="No teammates yet"
          description="Add someone above to get started."
        />
      ) : (
        <div className="divide-y rounded-lg border">
          {members.map((member) => (
            <div key={member.userId} className="flex items-center justify-between px-4 py-3">
              <div className="flex items-center gap-3">
                <Avatar className="size-8">
                  <AvatarFallback className="text-xs">{member.email[0]?.toUpperCase()}</AvatarFallback>
                </Avatar>
                <div>
                  <p className="text-sm font-medium">{member.email}</p>
                  <p className="text-muted-foreground text-xs">Joined {formatDate(member.createdAt)}</p>
                </div>
              </div>
              <Badge variant="outline" className="capitalize">
                {member.role}
              </Badge>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}
