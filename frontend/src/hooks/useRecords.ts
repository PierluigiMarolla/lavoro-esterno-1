import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as recordsApi from "@/api/records";
import type { RecordSearchFilters } from "@/types";

export function useRecordSearch(filters: RecordSearchFilters) {
  return useQuery({
    queryKey: ["records", "search", filters],
    queryFn: () => recordsApi.searchRecords(filters),
    // Search is opt-in: only run once a phone or at least one filter has been provided,
    // so the page doesn't fire an unbounded query on first render.
    enabled: Boolean(filters.phone || filters.source || filters.status || filters.dateFrom),
    placeholderData: (previous) => previous,
  });
}

export function useRecordOverview(id: string) {
  return useQuery({ queryKey: ["records", id, "overview"], queryFn: () => recordsApi.fetchRecordOverview(id), enabled: Boolean(id) });
}

export function useRecordOccurrences(id: string) {
  return useQuery({ queryKey: ["records", id, "occurrences"], queryFn: () => recordsApi.fetchRecordOccurrences(id), enabled: Boolean(id) });
}

export function useRecordMedia(id: string) {
  return useQuery({ queryKey: ["records", id, "media"], queryFn: () => recordsApi.fetchRecordMedia(id), enabled: Boolean(id) });
}

export function useRecordHistory(id: string) {
  return useQuery({ queryKey: ["records", id, "history"], queryFn: () => recordsApi.fetchRecordHistory(id), enabled: Boolean(id) });
}

export function useRecordAiSummary(id: string) {
  return useQuery({ queryKey: ["records", id, "ai-summary"], queryFn: () => recordsApi.fetchRecordAiSummary(id), enabled: Boolean(id) });
}

export function useRegenerateAiSummary(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: () => recordsApi.regenerateRecordAiSummary(id),
    onSuccess: (data) => {
      queryClient.setQueryData(["records", id, "ai-summary"], data);
    },
  });
}
