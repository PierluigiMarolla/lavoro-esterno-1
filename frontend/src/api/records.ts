import { apiRequest } from "./client";
import type {
  RecordAiSummary,
  RecordHistoryEvent,
  RecordMedia,
  RecordOccurrence,
  RecordOverview,
  RecordSearchFilters,
  RecordSearchResponse,
} from "@/types";

function toQueryString(filters: RecordSearchFilters): string {
  const params = new URLSearchParams();
  if (filters.phone) params.set("phone", filters.phone);
  if (filters.source) params.set("source", filters.source);
  if (filters.status) params.set("status", filters.status);
  if (filters.dateFrom) params.set("date_from", filters.dateFrom);
  if (filters.dateTo) params.set("date_to", filters.dateTo);
  params.set("page", String(filters.page ?? 1));
  params.set("page_size", String(filters.pageSize ?? 25));
  return params.toString();
}

export function searchRecords(filters: RecordSearchFilters): Promise<RecordSearchResponse> {
  return apiRequest<RecordSearchResponse>(`/records/search?${toQueryString(filters)}`);
}

export function fetchRecordOverview(id: string): Promise<RecordOverview> {
  return apiRequest<RecordOverview>(`/records/${id}`);
}

export function fetchRecordOccurrences(id: string): Promise<RecordOccurrence[]> {
  return apiRequest<RecordOccurrence[]>(`/records/${id}/occurrences`);
}

export function fetchRecordMedia(id: string): Promise<RecordMedia[]> {
  return apiRequest<RecordMedia[]>(`/records/${id}/media`);
}

export function fetchRecordHistory(id: string): Promise<RecordHistoryEvent[]> {
  return apiRequest<RecordHistoryEvent[]>(`/records/${id}/history`);
}

export function fetchRecordAiSummary(id: string): Promise<RecordAiSummary> {
  return apiRequest<RecordAiSummary>(`/records/${id}/ai-summary`);
}

// Triggers a fresh AI summary generation job; the summary query should be
// invalidated/refetched by the caller once this resolves.
export function regenerateRecordAiSummary(id: string): Promise<RecordAiSummary> {
  return apiRequest<RecordAiSummary>(`/records/${id}/ai-summary/regenerate`, { method: "POST" });
}
