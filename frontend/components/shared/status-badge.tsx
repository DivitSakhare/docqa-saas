import { CheckCircle2, Loader2, XCircle } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import { cn } from "@/lib/utils";
import type { DocumentStatus } from "@/lib/types";

const CONFIG: Record<DocumentStatus, { label: string; className: string; icon: React.ReactNode }> = {
  pending: {
    label: "Processing",
    className: "bg-amber-500/10 text-amber-600 dark:text-amber-400 border-amber-500/20",
    icon: <Loader2 className="size-3 animate-spin" />,
  },
  ready: {
    label: "Ready",
    className: "bg-emerald-500/10 text-emerald-600 dark:text-emerald-400 border-emerald-500/20",
    icon: <CheckCircle2 className="size-3" />,
  },
  failed: {
    label: "Failed",
    className: "bg-destructive/10 text-destructive border-destructive/20",
    icon: <XCircle className="size-3" />,
  },
};

export function StatusBadge({ status }: { status: DocumentStatus }) {
  const config = CONFIG[status];
  return (
    <Badge variant="outline" className={cn("gap-1 font-normal", config.className)}>
      {config.icon}
      {config.label}
    </Badge>
  );
}
