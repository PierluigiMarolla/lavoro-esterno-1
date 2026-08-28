import { useState } from "react";
import { useAdminUsers, useUpdateAdminUserRole, useSuspendAdminUser, useAuditLog } from "@/hooks/useAdmin";
import Icon from "@/components/ui/Icon";
import Avatar from "@/components/ui/Avatar";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import Select from "@/components/ui/Select";
import { EmptyRow, ErrorRow, LoadingRow, Table, TBody, Td, Th, THead, Tr } from "@/components/ui/Table";
import { cn } from "@/lib/cn";
import type { AdminUser, UserRole } from "@/types";

// Replicates desing/admin_lavoro_esterno/code.html.
//
// The mockup's tab strip is reused here with local useState instead of the
// router-driven <Tabs> component: /admin is a single flat route (no nested
// paths per tab in App.tsx), so there is nothing for NavLink to match against.

type AdminTab = "users" | "source-priorities" | "classifiers" | "audit-log";

const TABS: { key: AdminTab; label: string }[] = [
  { key: "users", label: "Users & Roles" },
  { key: "source-priorities", label: "Source Priorities" },
  { key: "classifiers", label: "Classifiers" },
  { key: "audit-log", label: "Audit Log" },
];

const ROLE_LABEL: Record<UserRole, string> = {
  admin: "Admin",
  operator: "Operator",
  viewer: "Viewer",
};

const STATUS_TONE: Record<AdminUser["status"], BadgeTone> = {
  active: "success",
  suspended: "warning",
  invited: "neutral",
};

function formatDateTime(iso: string | null): string {
  if (!iso) return "Never";
  return new Date(iso).toLocaleString([], { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" });
}

export default function AdminPage() {
  const [tab, setTab] = useState<AdminTab>("users");

  return (
    <div className="flex flex-col gap-6">
      <div className="flex flex-col gap-4">
        <div className="flex justify-between items-end">
          <div>
            <h2 className="text-headline-md text-on-surface">Administration</h2>
            <p className="text-body-md text-on-surface-variant mt-1">
              Manage platform configuration, user access, and audit trails.
            </p>
          </div>
        </div>

        {/* Local tab strip — styled like components/ui/Tabs.tsx but click-driven */}
        <div className="border-b border-border flex gap-1">
          {TABS.map((t) => (
            <button
              key={t.key}
              onClick={() => setTab(t.key)}
              className={cn(
                "px-4 py-2.5 text-label-sm font-medium border-b-2 -mb-px transition-colors",
                tab === t.key
                  ? "border-primary text-primary"
                  : "border-transparent text-on-surface-variant hover:text-on-surface",
              )}
            >
              {t.label}
            </button>
          ))}
        </div>
      </div>

      {tab === "users" && <UsersTab />}
      {tab === "source-priorities" && (
        <ComingSoon icon="low_priority" title="Source Priorities" message="Priority configuration for data sources is not yet implemented." />
      )}
      {tab === "classifiers" && (
        <ComingSoon icon="category" title="Classifiers" message="Classifier management is not yet implemented." />
      )}
      {tab === "audit-log" && <AuditLogTab />}
    </div>
  );
}

function UsersTab() {
  const users = useAdminUsers();
  const updateRole = useUpdateAdminUserRole();
  const suspend = useSuspendAdminUser();

  return (
    <div className="bg-white border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] flex flex-col">
      <Table>
        <THead>
          <Tr className="hover:bg-transparent">
            <Th>User</Th>
            <Th>Email</Th>
            <Th>Role</Th>
            <Th>Status</Th>
            <Th>Last Login</Th>
            <Th className="text-center">MFA</Th>
            <Th className="text-right">Actions</Th>
          </Tr>
        </THead>
        <TBody>
          {users.isLoading && <LoadingRow colSpan={7} />}
          {users.isError && <ErrorRow colSpan={7} message="Failed to load users." />}
          {users.data && users.data.length === 0 && <EmptyRow colSpan={7} message="No users found." />}
          {users.data?.map((user) => (
            <Tr key={user.id}>
              <Td>
                <div className="flex items-center gap-3">
                  <Avatar name={user.name} size={28} />
                  <span className="font-medium text-on-surface">{user.name}</span>
                </div>
              </Td>
              <Td className="text-on-surface-variant font-mono text-mono-data">{user.email}</Td>
              <Td>
                <Select
                  value={user.role}
                  disabled={updateRole.isPending}
                  onChange={(e) => updateRole.mutate({ id: user.id, role: e.target.value as UserRole })}
                  className="text-label-sm py-1"
                >
                  {(Object.keys(ROLE_LABEL) as UserRole[]).map((role) => (
                    <option key={role} value={role}>
                      {ROLE_LABEL[role]}
                    </option>
                  ))}
                </Select>
              </Td>
              <Td>
                <Badge tone={STATUS_TONE[user.status]}>{user.status.toUpperCase()}</Badge>
              </Td>
              <Td className="text-on-surface-variant font-mono text-mono-data">{formatDateTime(user.lastLoginAt)}</Td>
              <Td className="text-center">
                {user.mfaEnabled ? (
                  <Icon name="verified_user" size={18} className="text-success" />
                ) : (
                  <Icon name="gpp_maybe" size={18} className="text-outline" />
                )}
              </Td>
              <Td className="text-right">
                <button
                  onClick={() => suspend.mutate(user.id)}
                  disabled={suspend.isPending || user.status === "suspended"}
                  className="text-label-sm font-medium text-on-surface-variant hover:text-error transition-colors disabled:opacity-40 disabled:pointer-events-none"
                >
                  Suspend
                </button>
              </Td>
            </Tr>
          ))}
        </TBody>
      </Table>
    </div>
  );
}

function AuditLogTab() {
  const auditLog = useAuditLog();

  return (
    <div className="bg-white border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] flex flex-col">
      <Table>
        <THead>
          <Tr className="hover:bg-transparent">
            <Th>Actor</Th>
            <Th>Action</Th>
            <Th>Target</Th>
            <Th>Time</Th>
          </Tr>
        </THead>
        <TBody>
          {auditLog.isLoading && <LoadingRow colSpan={4} />}
          {auditLog.isError && <ErrorRow colSpan={4} message="Failed to load audit log." />}
          {auditLog.data && auditLog.data.length === 0 && <EmptyRow colSpan={4} message="No audit events yet." />}
          {auditLog.data?.map((entry) => (
            <Tr key={entry.id}>
              <Td className="text-on-surface font-medium">{entry.actor}</Td>
              <Td className="text-on-surface-variant">{entry.action}</Td>
              <Td className="text-on-surface-variant font-mono text-mono-data">{entry.target}</Td>
              <Td className="text-on-surface-variant font-mono text-mono-data">{formatDateTime(entry.occurredAt)}</Td>
            </Tr>
          ))}
        </TBody>
      </Table>
    </div>
  );
}

function ComingSoon({ icon, title, message }: { icon: string; title: string; message: string }) {
  return (
    <div className="bg-white border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] flex flex-col items-center justify-center gap-3 py-20 text-center">
      <div className="w-12 h-12 rounded-full bg-surface-container-low flex items-center justify-center text-on-surface-variant">
        <Icon name={icon} size={24} />
      </div>
      <h3 className="text-headline-sm text-on-surface">{title}</h3>
      <p className="text-body-md text-on-surface-variant max-w-sm">{message}</p>
    </div>
  );
}
