"use client";

import { useState } from "react";
import { SendHorizontal } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";

export function ChatInput({ onSend, disabled }: { onSend: (question: string) => void; disabled: boolean }) {
  const [value, setValue] = useState("");

  function handleSubmit() {
    const trimmed = value.trim();
    if (!trimmed || disabled) return;
    onSend(trimmed);
    setValue("");
  }

  return (
    <div className="flex items-end gap-2 border-t p-3">
      <Textarea
        value={value}
        onChange={(event) => setValue(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === "Enter" && !event.shiftKey) {
            event.preventDefault();
            handleSubmit();
          }
        }}
        placeholder="Ask a question about your documents…"
        rows={1}
        className="min-h-10 resize-none"
        disabled={disabled}
      />
      <Button size="icon" onClick={handleSubmit} disabled={disabled || !value.trim()} aria-label="Send">
        <SendHorizontal className="size-4" />
      </Button>
    </div>
  );
}
