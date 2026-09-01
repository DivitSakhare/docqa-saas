"use client";

import { useState } from "react";
import { History, MessageSquare, Plus } from "lucide-react";
import { toast } from "sonner";

import { ChatInput } from "@/components/chat/chat-input";
import { ConversationList } from "@/components/chat/conversation-list";
import { MessageThread } from "@/components/chat/message-thread";
import { EmptyState } from "@/components/shared/empty-state";
import { Button } from "@/components/ui/button";
import { Sheet, SheetContent, SheetHeader, SheetTitle, SheetTrigger } from "@/components/ui/sheet";
import { useSendMessage } from "@/hooks/use-chat";
import { useConversation } from "@/hooks/use-conversations";
import { ClientApiError } from "@/lib/api";
import type { Message } from "@/lib/types";

export default function ChatPage() {
  const [activeId, setActiveId] = useState<string | null>(null);
  const [mobileHistoryOpen, setMobileHistoryOpen] = useState(false);

  const { data: conversation, isLoading } = useConversation(activeId);
  const sendMessage = useSendMessage();

  // The query cache (populated by useSendMessage's onSuccess) is the only
  // place a conversation's messages live — no separate local copy, so
  // there's nothing that can end up duplicated against it.
  const messages: Message[] = conversation?.messages ?? [];
  const pendingQuestion = sendMessage.isPending ? sendMessage.variables?.question : undefined;

  async function handleSend(question: string) {
    try {
      const result = await sendMessage.mutateAsync({
        question,
        conversationId: activeId ?? undefined,
      });
      if (!activeId) setActiveId(result.conversationId);
    } catch (error) {
      const message = error instanceof ClientApiError ? error.message : "Could not send that message.";
      toast.error(message);
    }
  }

  function handleSelect(id: string) {
    setActiveId(id);
    setMobileHistoryOpen(false);
  }

  function handleNew() {
    setActiveId(null);
    setMobileHistoryOpen(false);
  }

  return (
    <div className="-m-4 flex h-[calc(100dvh-3.5rem)] lg:-m-8">
      <div className="hidden w-64 shrink-0 sm:block">
        <ConversationList activeId={activeId} onSelect={handleSelect} onNew={handleNew} />
      </div>

      <div className="flex flex-1 flex-col">
        <div className="flex items-center justify-between border-b p-3 sm:hidden">
          <Sheet open={mobileHistoryOpen} onOpenChange={setMobileHistoryOpen}>
            <SheetTrigger asChild>
              <Button variant="outline" size="sm">
                <History className="size-4" />
                History
              </Button>
            </SheetTrigger>
            <SheetContent side="left" className="w-64 p-0">
              <SheetHeader className="sr-only">
                <SheetTitle>Conversations</SheetTitle>
              </SheetHeader>
              <ConversationList activeId={activeId} onSelect={handleSelect} onNew={handleNew} />
            </SheetContent>
          </Sheet>
          <Button variant="ghost" size="sm" onClick={handleNew}>
            <Plus className="size-4" />
            New
          </Button>
        </div>

        {messages.length === 0 && !pendingQuestion && !isLoading ? (
          <div className="flex flex-1 items-center justify-center p-8">
            <EmptyState
              icon={<MessageSquare className="size-8" />}
              title="Start a conversation"
              description="Ask a question about any document you've uploaded — answers are grounded in your own documents with citations."
            />
          </div>
        ) : (
          <MessageThread
            messages={messages}
            isLoading={isLoading && activeId !== null}
            pendingQuestion={pendingQuestion}
          />
        )}
        <ChatInput onSend={handleSend} disabled={sendMessage.isPending} />
      </div>
    </div>
  );
}
