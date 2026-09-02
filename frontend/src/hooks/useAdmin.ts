import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import * as adminApi from "@/api/admin";
import type { UserRole } from "@/types";

const usersKey = ["admin", "users"] as const;

export function useAdminUsers() {
  return useQuery({ queryKey: usersKey, queryFn: adminApi.fetchAdminUsers });
}

export function useUpdateAdminUserRole() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, role }: { id: string; role: UserRole }) => adminApi.updateAdminUserRole(id, role),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}

export function useUpdateClearPhonePermission() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: ({ id, enabled }: { id: string; enabled: boolean }) =>
      adminApi.updateClearPhonePermission(id, enabled),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}

export function useSuspendAdminUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: adminApi.suspendAdminUser,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}

export function useCreateAdminUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: adminApi.createAdminUser,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}

export function useResetAdminUserTwoFactor() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: adminApi.resetAdminUserTwoFactor,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}

export function useAuditLog() {
  return useQuery({ queryKey: ["admin", "audit-log"], queryFn: adminApi.fetchAuditLog });
}

const erasureKey = ["admin", "erasure-requests"] as const;

export function useErasureRequests() {
  return useQuery({
    queryKey: erasureKey,
    queryFn: adminApi.fetchErasureRequests,
    refetchInterval: (query) =>
      query.state.data?.some((item) => item.status === "pending" || item.status === "processing")
        ? 3000
        : false,
  });
}

export function useCreateErasureRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: adminApi.createErasureRequest,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: erasureKey }),
  });
}

export function useConfirmErasureRequest() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: adminApi.confirmErasureRequest,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: erasureKey }),
  });
}
