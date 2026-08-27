import { apiRequest } from "./client";
import type { ExportJob, ExportType } from "@/types";

export function fetchExportJobs(): Promise<ExportJob[]> {
  return apiRequest<ExportJob[]>("/exports");
}

export function createExportJob(type: ExportType, recordIds?: string[]): Promise<ExportJob> {
  return apiRequest<ExportJob>("/exports", {
    method: "POST",
    body: { type, record_ids: recordIds },
  });
}

export function retryExportJob(id: string): Promise<ExportJob> {
  return apiRequest<ExportJob>(`/exports/${id}/retry`, { method: "POST" });
}

// The backend streams the file; we just resolve the signed URL to open/download.
export function getExportDownloadUrl(id: string): Promise<{ url: string }> {
  return apiRequest<{ url: string }>(`/exports/${id}/download`);
}
