"use client";

import { useQuery } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { ConversationDetail, ConversationSummary } from "@/lib/types";

export function useConversations() {
  return useQuery({
    queryKey: ["conversations"],
    queryFn: () => apiFetch<ConversationSummary[]>("/api/conversations"),
  });
}

export function useConversation(conversationId: string | null) {
  return useQuery({
    queryKey: ["conversations", conversationId],
    queryFn: () => apiFetch<ConversationDetail>(`/api/conversations/${conversationId}`),
    enabled: conversationId !== null,
  });
}
