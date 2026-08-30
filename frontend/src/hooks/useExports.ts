import { useMutation, useQuery, useQueryClient, type Query } from "@tanstack/react-query";
import * as exportsApi from "@/api/exports";
import type { ExportJob, ExportType } from "@/types";

const jobsKey = ["exports", "jobs"] as const;

const ACTIVE_POLL_INTERVAL_MS = 3000;

export function useExportJobs() {
  // Poll frequently while any job is still pending/processing so status
  // updates (e.g. completion, failure) show up without a manual refresh;
  // stop polling entirely once every job has settled to avoid idle traffic.
  return useQuery({
    queryKey: jobsKey,
    queryFn: exportsApi.fetchExportJobs,
    refetchInterval: (query: Query<ExportJob[]>) => {
      // ExportStatus is currently "ready" | "processing" | "failed" (no
      // separate "pending" state in the API today); "processing" is the
      // only non-terminal status, so that's what keeps polling alive.
      const jobs = query.state.data;
      const hasActiveJob = jobs?.some((job) => job.status === "processing");
      return hasActiveJob ? ACTIVE_POLL_INTERVAL_MS : false;
    },
  });
}

export function useCreateExportJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ type, recordIds }: { type: ExportType; recordIds?: string[] }) =>
      exportsApi.createExportJob(type, recordIds),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: jobsKey }),
  });
}

export function useRetryExportJob() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: exportsApi.retryExportJob,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: jobsKey }),
  });
}
