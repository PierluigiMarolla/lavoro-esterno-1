import { useQuery } from "@tanstack/react-query";
import { fetchDashboardKpis, fetchRecentActivity, fetchScrapingActivity, fetchSourceHealth } from "@/api/dashboard";

export function useDashboardKpis() {
  return useQuery({ queryKey: ["dashboard", "kpis"], queryFn: fetchDashboardKpis });
}

export function useScrapingActivity() {
  return useQuery({ queryKey: ["dashboard", "scraping-activity"], queryFn: fetchScrapingActivity, refetchInterval: 15000 });
}

export function useSourceHealth() {
  return useQuery({ queryKey: ["dashboard", "source-health"], queryFn: fetchSourceHealth });
}

export function useRecentActivity() {
  return useQuery({ queryKey: ["dashboard", "activity"], queryFn: fetchRecentActivity, refetchInterval: 30000 });
}
