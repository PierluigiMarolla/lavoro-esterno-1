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

export function useSuspendAdminUser() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: adminApi.suspendAdminUser,
    onSuccess: () => queryClient.invalidateQueries({ queryKey: usersKey }),
  });
}

export function useAuditLog() {
  return useQuery({ queryKey: ["admin", "audit-log"], queryFn: adminApi.fetchAuditLog });
}
