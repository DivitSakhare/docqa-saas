"use client";

import { useEffect, useRef } from "react";
import { Bot, User as UserIcon } from "lucide-react";

import { CitationChip } from "@/components/shared/citation-chip";
import { ScrollArea } from "@/components/ui/scroll-area";
import { Skeleton } from "@/components/ui/skeleton";
import type { Message } from "@/lib/types";
import { cn } from "@/lib/utils";

export function MessageThread({
  messages,
  isLoading,
  pendingQuestion,
}: {
  messages: Message[];
  isLoading: boolean;
  /** The question just submitted, shown as a trailing bubble while its
   * answer is in flight. Purely derived from the mutation's own pending
   * state (see chat/page.tsx) — never written into `messages` itself, so
   * there's no persisted copy left behind for a later refetch to collide
   * with. */
  pendingQuestion?: string;
}) {
  const bottomRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages.length, pendingQuestion]);

  if (isLoading) {
    return (
      <div className="space-y-4 p-4">
        <Skeleton className="h-16 w-2/3" />
        <Skeleton className="ml-auto h-10 w-1/2" />
      </div>
    );
  }

  return (
    <ScrollArea className="flex-1">
      <div className="flex flex-col gap-4 p-4">
        {messages.map((message) => (
          <MessageBubble key={message.id} message={message} />
        ))}
        {pendingQuestion && (
          <>
            <MessageBubble
              message={{
                id: "pending-question",
                role: "user",
                content: pendingQuestion,
                citations: null,
                createdAt: new Date().toISOString(),
              }}
            />
            <ThinkingBubble />
          </>
        )}
        <div ref={bottomRef} />
      </div>
    </ScrollArea>
  );
}

function ThinkingBubble() {
  return (
    <div className="flex gap-3">
      <div className="bg-muted flex size-7 shrink-0 items-center justify-center rounded-full">
        <Bot className="size-4" />
      </div>
      <div className="bg-muted flex items-center gap-1 rounded-lg px-3 py-2.5">
        <span className="bg-muted-foreground/60 size-1.5 animate-bounce rounded-full [animation-delay:-0.3s]" />
        <span className="bg-muted-foreground/60 size-1.5 animate-bounce rounded-full [animation-delay:-0.15s]" />
        <span className="bg-muted-foreground/60 size-1.5 animate-bounce rounded-full" />
      </div>
    </div>
  );
}

function MessageBubble({ message }: { message: Message }) {
  const isUser = message.role === "user";
  // The backend returns no citations specifically for its canned "not
  // enough information" reply (see chat_score_threshold in
  // docs/ARCHITECTURE.md) — style that reply distinctly rather than
  // pretending it's a normal grounded answer.
  const isUngrounded = !isUser && (!message.citations || message.citations.length === 0);

  return (
    <div className={cn("flex gap-3", isUser && "flex-row-reverse")}>
      <div
        className={cn(
          "flex size-7 shrink-0 items-center justify-center rounded-full",
          isUser ? "bg-primary text-primary-foreground" : "bg-muted"
        )}
      >
        {isUser ? <UserIcon className="size-4" /> : <Bot className="size-4" />}
      </div>
      <div className={cn("flex max-w-[75%] flex-col gap-1.5", isUser && "items-end")}>
        <div
          className={cn(
            "rounded-lg px-3 py-2 text-sm",
            isUser
              ? "bg-primary text-primary-foreground"
              : isUngrounded
                ? "bg-muted text-muted-foreground italic"
                : "bg-muted"
          )}
        >
          {message.content}
        </div>
        {message.citations && message.citations.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {message.citations.map((citation, index) => (
              <CitationChip key={`${citation.documentId}-${citation.pageNumber}-${index}`} citation={citation} />
            ))}
          </div>
        )}
      </div>
    </div>
  );
}
