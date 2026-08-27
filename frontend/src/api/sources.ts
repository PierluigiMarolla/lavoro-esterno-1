import { apiRequest } from "./client";
import type { Source } from "@/types";

export interface SourcesSummary {
  total: number;
  active: number;
  degraded: number;
  offline: number;
}

export function fetchSources(): Promise<Source[]> {
  return apiRequest<Source[]>("/sources");
}

export function fetchSourcesSummary(): Promise<SourcesSummary> {
  return apiRequest<SourcesSummary>("/sources/summary");
}

export function runSourceScan(id: string): Promise<void> {
  return apiRequest<void>(`/sources/${id}/scan`, { method: "POST" });
}

export function pauseSource(id: string): Promise<void> {
  return apiRequest<void>(`/sources/${id}/pause`, { method: "POST" });
}

export function disableSource(id: string): Promise<void> {
  return apiRequest<void>(`/sources/${id}/disable`, { method: "POST" });
}
