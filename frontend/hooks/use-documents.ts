"use client";

import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { apiFetch } from "@/lib/api";
import type { DocumentSummary, DocumentUploadResult } from "@/lib/types";

export function useDocuments() {
  return useQuery({
    queryKey: ["documents"],
    queryFn: () => apiFetch<DocumentSummary[]>("/api/documents"),
    // Keeps polling only while something is still processing — a brand
    // new tenant with no documents, or one where everything already
    // settled to ready/failed, stops refetching on its own.
    refetchInterval: (query) =>
      query.state.data?.some((doc) => doc.status === "pending") ? 3000 : false,
  });
}

export function useUploadDocument() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (file: File) => {
      const formData = new FormData();
      formData.append("file", file);
      return apiFetch<DocumentUploadResult>("/api/documents", {
        method: "POST",
        body: formData,
      });
    },
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["documents"] });
    },
  });
}
