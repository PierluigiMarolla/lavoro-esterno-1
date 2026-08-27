import { apiRequest } from "./client";
import type { AdminUser, UserRole } from "@/types";

export function fetchAdminUsers(): Promise<AdminUser[]> {
  return apiRequest<AdminUser[]>("/admin/users");
}

export function updateAdminUserRole(id: string, role: UserRole): Promise<AdminUser> {
  return apiRequest<AdminUser>(`/admin/users/${id}`, { method: "PATCH", body: { role } });
}

export function suspendAdminUser(id: string): Promise<AdminUser> {
  return apiRequest<AdminUser>(`/admin/users/${id}/suspend`, { method: "POST" });
}

export interface AuditLogEntry {
  id: string;
  actor: string;
  action: string;
  target: string;
  occurredAt: string;
}

export function fetchAuditLog(): Promise<AuditLogEntry[]> {
  return apiRequest<AuditLogEntry[]>("/admin/audit-log");
}
