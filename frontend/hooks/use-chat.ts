"use client";

import { useMutation, useQueryClient } from "@tanstack/react-query";

import type { ChatInput, ChatResult, ConversationDetail, Message } from "@/lib/types";
import { apiFetch } from "@/lib/api";

export function useSendMessage() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: ChatInput) =>
      apiFetch<ChatResult>("/api/chat", { method: "POST", body: JSON.stringify(input) }),
    onSuccess: (result, variables) => {
      // Writes the confirmed turn straight into this conversation's cache
      // instead of invalidating it — invalidating here previously raced a
      // background refetch against the page's own optimistic state and
      // produced a duplicated turn once both landed. The query cache is
      // the only place this conversation's messages live now.
      const now = new Date().toISOString();
      const userMessage: Message = {
        id: `${result.conversationId}-${now}-user`,
        role: "user",
        content: variables.question,
        citations: null,
        createdAt: now,
      };
      const assistantMessage: Message = {
        id: `${result.conversationId}-${now}-assistant`,
        role: "assistant",
        content: result.answer,
        citations: result.citations,
        createdAt: now,
      };
      queryClient.setQueryData<ConversationDetail>(["conversations", result.conversationId], (old) =>
        old
          ? { ...old, updatedAt: now, messages: [...old.messages, userMessage, assistantMessage] }
          : { id: result.conversationId, createdAt: now, updatedAt: now, messages: [userMessage, assistantMessage] }
      );
      queryClient.invalidateQueries({ queryKey: ["conversations"] });
    },
  });
}
