"use client";

import { Plus } from "lucide-react";

import { Button } from "@/components/ui/button";
import { ScrollArea } from "@/components/ui/scroll-area";
import { useConversations } from "@/hooks/use-conversations";
import { cn } from "@/lib/utils";

function formatDate(iso: string) {
  return new Date(iso).toLocaleString(undefined, { dateStyle: "medium", timeStyle: "short" });
}

export function ConversationList({
  activeId,
  onSelect,
  onNew,
}: {
  activeId: string | null;
  onSelect: (id: string) => void;
  onNew: () => void;
}) {
  const { data: conversations, isLoading } = useConversations();

  return (
    <div className="flex h-full flex-col border-r">
      <div className="flex items-center justify-between border-b p-3">
        <span className="text-sm font-medium">Conversations</span>
        <Button size="icon-sm" variant="outline" onClick={onNew} aria-label="New conversation">
          <Plus className="size-4" />
        </Button>
      </div>
      <ScrollArea className="flex-1">
        <div className="flex flex-col gap-1 p-2">
          {isLoading && <p className="text-muted-foreground p-2 text-xs">Loading…</p>}
          {!isLoading && conversations?.length === 0 && (
            <p className="text-muted-foreground p-2 text-xs">No conversations yet.</p>
          )}
          {conversations?.map((conversation) => (
            <button
              key={conversation.id}
              onClick={() => onSelect(conversation.id)}
              className={cn(
                "rounded-md px-3 py-2 text-left text-sm transition-colors",
                activeId === conversation.id ? "bg-secondary text-secondary-foreground" : "hover:bg-muted"
              )}
            >
              <p className="truncate font-medium">{formatDate(conversation.updatedAt)}</p>
              <p className="text-muted-foreground text-xs">
                {conversation.messageCount} message{conversation.messageCount === 1 ? "" : "s"}
              </p>
            </button>
          ))}
        </div>
      </ScrollArea>
    </div>
  );
}
