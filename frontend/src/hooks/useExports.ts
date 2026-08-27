import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as exportsApi from "@/api/exports";
import type { ExportType } from "@/types";

const jobsKey = ["exports", "jobs"] as const;

export function useExportJobs() {
  // Poll while any job might still be processing; harmless if all are settled.
  return useQuery({ queryKey: jobsKey, queryFn: exportsApi.fetchExportJobs, refetchInterval: 10000 });
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
