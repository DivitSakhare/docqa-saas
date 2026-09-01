"use client";

import { useRef, useState } from "react";
import { Upload } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { useUploadDocument } from "@/hooks/use-documents";
import { ClientApiError } from "@/lib/api";
import { cn } from "@/lib/utils";

const ACCEPTED_TYPES = [
  "application/pdf",
  "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
];

export function UploadDropzone() {
  const upload = useUploadDocument();
  const inputRef = useRef<HTMLInputElement>(null);
  const [dragOver, setDragOver] = useState(false);

  async function handleFile(file: File) {
    if (!ACCEPTED_TYPES.includes(file.type)) {
      toast.error("Only PDF and Word (.docx) files are supported right now.");
      return;
    }
    try {
      await upload.mutateAsync(file);
      toast.success(`${file.name} uploaded — processing in the background.`);
    } catch (error) {
      const message = error instanceof ClientApiError ? error.message : "Upload failed.";
      toast.error(message);
    }
  }

  return (
    <div
      onDragOver={(event) => {
        event.preventDefault();
        setDragOver(true);
      }}
      onDragLeave={() => setDragOver(false)}
      onDrop={(event) => {
        event.preventDefault();
        setDragOver(false);
        const file = event.dataTransfer.files?.[0];
        if (file) handleFile(file);
      }}
      className={cn(
        "flex flex-col items-center justify-center gap-2 rounded-lg border border-dashed p-8 text-center transition-colors",
        dragOver ? "border-primary bg-primary/5" : "border-border"
      )}
    >
      <Upload className="text-muted-foreground size-6" />
      <p className="text-sm font-medium">Drag and drop a PDF or Word doc here</p>
      <p className="text-muted-foreground text-xs">or</p>
      <Button
        variant="outline"
        size="sm"
        disabled={upload.isPending}
        onClick={() => inputRef.current?.click()}
      >
        {upload.isPending ? "Uploading…" : "Browse files"}
      </Button>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPTED_TYPES.join(",")}
        className="hidden"
        onChange={(event) => {
          const file = event.target.files?.[0];
          if (file) handleFile(file);
          event.target.value = "";
        }}
      />
    </div>
  );
}
