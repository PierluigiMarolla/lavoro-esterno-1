import { useMemo, useState, type FormEvent } from "react";
import {
  useAdminUsers,
  useUpdateAdminUserRole,
  useSuspendAdminUser,
  useAuditLog,
  useCreateAdminUser,
  useResetAdminUserTwoFactor,
} from "@/hooks/useAdmin";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/api/client";
import { describeError } from "@/lib/errors";
import Icon from "@/components/ui/Icon";
import Avatar from "@/components/ui/Avatar";
import Badge, { type BadgeTone } from "@/components/ui/Badge";
import Select from "@/components/ui/Select";
import Button from "@/components/ui/Button";
import Dialog from "@/components/ui/Dialog";
import ErrorState from "@/components/ui/ErrorState";
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

// True when the mutation failed specifically because the requesting admin
// hasn't enabled 2FA yet (server-side `require_admin_with_2fa`) — see
// src/api/admin.ts:createAdminUser. Worth a dedicated message instead of the
// generic "Access denied" describeError() would otherwise show for a 403.
function isMfaSetupRequiredError(error: unknown): boolean {
  if (!(error instanceof ApiError) || error.status !== 403) return false;
  const detail = (error.body as { detail?: { error_code?: string } } | undefined)?.detail;
  return detail?.error_code === "mfa_setup_required";
}

export default function AdminPage() {
  const { user } = useAuth();
  const [tab, setTab] = useState<AdminTab>("users");

  if (user && user.role !== "admin") {
    return (
      <div className="bg-surface-container-lowest border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)]">
        <ErrorState
          error={new ApiError(403, "You need admin privileges to view this page.")}
          className="py-16"
        />
      </div>
    );
  }

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
  const [createOpen, setCreateOpen] = useState(false);
  const [resetTarget, setResetTarget] = useState<AdminUser | null>(null);

  return (
    <div className="flex flex-col gap-4">
      <div className="flex justify-end">
        <Button onClick={() => setCreateOpen(true)}>
          <Icon name="person_add" size={18} />
          Create user
        </Button>
      </div>

      <div className="bg-surface-container-lowest border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] flex flex-col">
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
            {users.isError && <ErrorRow colSpan={7} error={users.error} onRetry={() => users.refetch()} />}
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
                  <div className="flex items-center justify-end gap-3">
                    <button
                      onClick={() => setResetTarget(user)}
                      disabled={!user.mfaEnabled}
                      title={user.mfaEnabled ? "Reset 2FA" : "2FA not enabled for this user"}
                      className="text-label-sm font-medium text-on-surface-variant hover:text-primary transition-colors disabled:opacity-40 disabled:pointer-events-none"
                    >
                      Reset 2FA
                    </button>
                    <button
                      onClick={() => suspend.mutate(user.id)}
                      disabled={suspend.isPending || user.status === "suspended"}
                      className="text-label-sm font-medium text-on-surface-variant hover:text-error transition-colors disabled:opacity-40 disabled:pointer-events-none"
                    >
                      Suspend
                    </button>
                  </div>
                </Td>
              </Tr>
            ))}
          </TBody>
        </Table>
      </div>

      <CreateUserDialog open={createOpen} onClose={() => setCreateOpen(false)} />
      <ResetTwoFactorDialog user={resetTarget} onClose={() => setResetTarget(null)} />
    </div>
  );
}

function CreateUserDialog({ open, onClose }: { open: boolean; onClose: () => void }) {
  const createUser = useCreateAdminUser();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [role, setRole] = useState<UserRole>("viewer");

  function handleClose() {
    createUser.reset();
    setEmail("");
    setPassword("");
    setRole("viewer");
    onClose();
  }

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    createUser.mutate(
      { email, password, role },
      {
        onSuccess: handleClose,
      },
    );
  }

  const mfaSetupRequired = isMfaSetupRequiredError(createUser.error);

  return (
    <Dialog open={open} onClose={handleClose} title="Create user">
      <form onSubmit={handleSubmit} className="flex flex-col gap-4">
        <div>
          <label htmlFor="create-user-email" className="text-label-sm text-on-surface-variant block mb-1">
            Email
          </label>
          <input
            id="create-user-email"
            type="email"
            required
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className="w-full py-2 px-3 border border-outline-variant rounded bg-surface text-body-md text-on-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container outline-none transition-colors"
          />
        </div>
        <div>
          <label htmlFor="create-user-password" className="text-label-sm text-on-surface-variant block mb-1">
            Password
          </label>
          <input
            id="create-user-password"
            type="password"
            required
            minLength={8}
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className="w-full py-2 px-3 border border-outline-variant rounded bg-surface text-body-md text-on-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container outline-none transition-colors"
          />
        </div>
        <div>
          <label htmlFor="create-user-role" className="text-label-sm text-on-surface-variant block mb-1">
            Role
          </label>
          <Select id="create-user-role" value={role} onChange={(e) => setRole(e.target.value as UserRole)} className="w-full">
            {(Object.keys(ROLE_LABEL) as UserRole[]).map((r) => (
              <option key={r} value={r}>
                {ROLE_LABEL[r]}
              </option>
            ))}
          </Select>
        </div>

        {createUser.isError && (
          <p className="text-body-md text-error">
            {mfaSetupRequired
              ? "You must have 2FA enabled to create users."
              : describeError(createUser.error).description}
          </p>
        )}

        <div className="flex justify-end gap-2 mt-2">
          <Button type="button" variant="secondary" onClick={handleClose}>
            Cancel
          </Button>
          <Button type="submit" disabled={createUser.isPending}>
            {createUser.isPending ? "Creating…" : "Create user"}
          </Button>
        </div>
      </form>
    </Dialog>
  );
}

function ResetTwoFactorDialog({ user, onClose }: { user: AdminUser | null; onClose: () => void }) {
  const resetTwoFactor = useResetAdminUserTwoFactor();

  function handleClose() {
    resetTwoFactor.reset();
    onClose();
  }

  function handleConfirm() {
    if (!user) return;
    resetTwoFactor.mutate(user.id, { onSuccess: handleClose });
  }

  return (
    <Dialog open={user !== null} onClose={handleClose} title="Reset 2FA">
      <div className="flex flex-col gap-4">
        <p className="text-body-md text-on-surface">
          Are you sure you want to disable 2FA for <span className="font-semibold">{user?.name}</span> (
          {user?.email})? They will need to set it up again on their next login.
        </p>
        {resetTwoFactor.isError && (
          <p className="text-body-md text-error">{describeError(resetTwoFactor.error).description}</p>
        )}
        <div className="flex justify-end gap-2">
          <Button type="button" variant="secondary" onClick={handleClose}>
            Cancel
          </Button>
          <Button type="button" variant="danger" onClick={handleConfirm} disabled={resetTwoFactor.isPending}>
            {resetTwoFactor.isPending ? "Resetting…" : "Reset 2FA"}
          </Button>
        </div>
      </div>
    </Dialog>
  );
}

function AuditLogTab() {
  const auditLog = useAuditLog();
  const [query, setQuery] = useState("");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  const filtered = useMemo(() => {
    if (!auditLog.data) return undefined;
    const q = query.trim().toLowerCase();
    const from = dateFrom ? new Date(dateFrom).getTime() : null;
    // Include the entire "to" day rather than only events at exactly midnight.
    const to = dateTo ? new Date(dateTo).getTime() + 24 * 60 * 60 * 1000 - 1 : null;

    return auditLog.data.filter((entry) => {
      if (q && !entry.actor.toLowerCase().includes(q) && !entry.action.toLowerCase().includes(q)) {
        return false;
      }
      const occurredAt = new Date(entry.occurredAt).getTime();
      if (from !== null && occurredAt < from) return false;
      if (to !== null && occurredAt > to) return false;
      return true;
    });
  }, [auditLog.data, query, dateFrom, dateTo]);

  return (
    <div className="bg-surface-container-lowest border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] flex flex-col">
      <div className="p-4 border-b border-border flex flex-wrap items-end gap-3">
        <div className="flex-1 min-w-[200px]">
          <label htmlFor="audit-log-query" className="text-label-sm text-on-surface-variant block mb-1">
            Search actor / action
          </label>
          <input
            id="audit-log-query"
            type="text"
            placeholder="Filter by actor or action..."
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            className="w-full py-2 px-3 border border-outline-variant rounded bg-surface text-body-md text-on-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container outline-none transition-colors"
          />
        </div>
        <div>
          <label htmlFor="audit-log-from" className="text-label-sm text-on-surface-variant block mb-1">
            From
          </label>
          <input
            id="audit-log-from"
            type="date"
            value={dateFrom}
            onChange={(e) => setDateFrom(e.target.value)}
            className="py-2 px-3 border border-outline-variant rounded bg-surface text-body-md text-on-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container outline-none transition-colors"
          />
        </div>
        <div>
          <label htmlFor="audit-log-to" className="text-label-sm text-on-surface-variant block mb-1">
            To
          </label>
          <input
            id="audit-log-to"
            type="date"
            value={dateTo}
            onChange={(e) => setDateTo(e.target.value)}
            className="py-2 px-3 border border-outline-variant rounded bg-surface text-body-md text-on-surface focus:ring-2 focus:ring-primary-container focus:border-primary-container outline-none transition-colors"
          />
        </div>
        {(query || dateFrom || dateTo) && (
          <button
            onClick={() => {
              setQuery("");
              setDateFrom("");
              setDateTo("");
            }}
            className="text-label-sm text-on-surface-variant hover:text-primary transition-colors py-2"
          >
            Clear filters
          </button>
        )}
      </div>
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
          {auditLog.isError && <ErrorRow colSpan={4} error={auditLog.error} onRetry={() => auditLog.refetch()} />}
          {filtered && filtered.length === 0 && (
            <EmptyRow colSpan={4} message={auditLog.data && auditLog.data.length > 0 ? "No audit events match the filters." : "No audit events yet."} />
          )}
          {filtered?.map((entry) => (
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
    <div className="bg-surface-container-lowest border border-border rounded-lg shadow-[0_1px_2px_rgba(0,0,0,0.02)] flex flex-col items-center justify-center gap-3 py-20 text-center">
      <div className="w-12 h-12 rounded-full bg-surface-container-low flex items-center justify-center text-on-surface-variant">
        <Icon name={icon} size={24} />
      </div>
      <h3 className="text-headline-sm text-on-surface">{title}</h3>
      <p className="text-body-md text-on-surface-variant max-w-sm">{message}</p>
    </div>
  );
}
