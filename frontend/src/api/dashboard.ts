import { apiRequest } from "./client";
import type { ActivityEvent, DashboardKpis, ScrapingActivity, SourceHealthBreakdown } from "@/types";

export function fetchDashboardKpis(): Promise<DashboardKpis> {
  return apiRequest<DashboardKpis>("/dashboard/kpis");
}

export function fetchScrapingActivity(): Promise<ScrapingActivity[]> {
  return apiRequest<ScrapingActivity[]>("/dashboard/scraping-activity");
}

export function fetchSourceHealth(): Promise<SourceHealthBreakdown> {
  return apiRequest<SourceHealthBreakdown>("/dashboard/source-health");
}

export function fetchRecentActivity(): Promise<ActivityEvent[]> {
  return apiRequest<ActivityEvent[]>("/dashboard/activity");
}
