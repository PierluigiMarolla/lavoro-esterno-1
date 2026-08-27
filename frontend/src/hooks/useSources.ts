import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as sourcesApi from "@/api/sources";

const sourcesKey = ["sources"] as const;
const summaryKey = ["sources", "summary"] as const;

export function useSources() {
  return useQuery({ queryKey: sourcesKey, queryFn: sourcesApi.fetchSources });
}

export function useSourcesSummary() {
  return useQuery({ queryKey: summaryKey, queryFn: sourcesApi.fetchSourcesSummary });
}

// Shared invalidation for the three source action mutations below — any of
// them can change status/health, so refresh both the list and the summary cards.
function useInvalidateSources() {
  const queryClient = useQueryClient();
  return () => {
    queryClient.invalidateQueries({ queryKey: sourcesKey });
    queryClient.invalidateQueries({ queryKey: summaryKey });
  };
}

export function useRunSourceScan() {
  const invalidate = useInvalidateSources();
  return useMutation({ mutationFn: sourcesApi.runSourceScan, onSuccess: invalidate });
}

export function usePauseSource() {
  const invalidate = useInvalidateSources();
  return useMutation({ mutationFn: sourcesApi.pauseSource, onSuccess: invalidate });
}

export function useDisableSource() {
  const invalidate = useInvalidateSources();
  return useMutation({ mutationFn: sourcesApi.disableSource, onSuccess: invalidate });
}
