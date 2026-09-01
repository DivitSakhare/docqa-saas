import { FileText } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { Citation } from "@/lib/types";

export function CitationChip({ citation }: { citation: Citation }) {
  return (
    <Badge variant="secondary" className="gap-1 font-normal">
      <FileText className="size-3" />
      {citation.filename} · p.{citation.pageNumber}
    </Badge>
  );
}
