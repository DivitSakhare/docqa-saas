"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { TeamMember, TeamMemberInput } from "@/lib/types";

export function useTeamMembers() {
  return useQuery({
    queryKey: ["team"],
    queryFn: () => apiFetch<TeamMember[]>("/api/team/members"),
  });
}

export function useAddTeamMember() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: TeamMemberInput) =>
      apiFetch<TeamMember>("/api/team/members", { method: "POST", body: JSON.stringify(input) }),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["team"] });
    },
  });
}
