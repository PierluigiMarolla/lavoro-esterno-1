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

export interface CreateUserInput {
  email: string;
  password: string;
  role: UserRole;
}

// POST /admin/users requires the requesting admin to have 2FA enabled
// (`require_admin_with_2fa` server-side) — a 403 here most likely means
// that, not a generic permissions problem; see AdminPage.tsx's error copy.
export function createAdminUser(input: CreateUserInput): Promise<AdminUser> {
  return apiRequest<AdminUser>("/admin/users", { method: "POST", body: input });
}

// The backend response here is `{ id, mfa_enabled }` (snake_case, no
// CamelModel — see backend/app/schemas/auth.py:TwoFactorResetResponse),
// unlike every other admin.ts call: mapped explicitly here rather than
// changing an established backend contract just for this one field.
interface TwoFactorResetResponseDto {
  id: string;
  mfa_enabled: boolean;
}

export async function resetAdminUserTwoFactor(id: string): Promise<{ id: string; mfaEnabled: boolean }> {
  const dto = await apiRequest<TwoFactorResetResponseDto>(`/admin/users/${id}/reset-2fa`, {
    method: "POST",
  });
  return { id: dto.id, mfaEnabled: dto.mfa_enabled };
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
