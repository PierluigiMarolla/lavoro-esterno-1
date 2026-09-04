import { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import Icon from "@/components/ui/Icon";
import Dialog from "@/components/ui/Dialog";
import { useTheme } from "@/context/ThemeContext";
import { useMarkAllNotificationsRead, useMarkNotificationRead, useNotifications, useSystemStatus } from "@/hooks/useOperations";

const SEGMENT_LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  records: "Records",
  sources: "Sources",
  exports: "Exports",
  admin: "Admin",
  overview: "Overview",
  occurrences: "Occurrences",
  media: "Media",
  "ai-summary": "AI Summary",
  history: "History",
  account: "Account",
};

// Builds "Lavoro Esterno / Records / <id> / Occurrences" from the current
// URL so every route gets a correct breadcrumb without per-page wiring.
function useBreadcrumb() {
  const { pathname } = useLocation();
  const segments = pathname.split("/").filter(Boolean);
  return segments.map((segment) => SEGMENT_LABELS[segment] ?? segment);
}

export default function Topbar() {
  const crumbs = useBreadcrumb();
  const { resolvedTheme, toggle } = useTheme();
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const [statusOpen, setStatusOpen] = useState(false);
  const notifications = useNotifications();
  const markRead = useMarkNotificationRead();
  const markAll = useMarkAllNotificationsRead();
  const system = useSystemStatus(statusOpen);

  return (
    <header className="flex justify-between items-center px-gutter w-full sticky top-0 z-40 bg-surface h-topbar-height shadow-[0_1px_3px_rgba(0,0,0,0.05)] border-b border-border">
      <nav aria-label="Breadcrumb" className="hidden md:flex">
        <ol className="flex items-center gap-2 text-label-sm text-on-surface-variant">
          <li>
            <Link to="/dashboard" className="hover:text-primary transition-colors">
              Lavoro Esterno
            </Link>
          </li>
          {crumbs.map((crumb, i) => (
            <li key={i} className="flex items-center gap-2">
              <Icon name="chevron_right" size={16} className="text-outline opacity-50" />
              <span className={i === crumbs.length - 1 ? "text-on-surface font-semibold" : ""}>{crumb}</span>
            </li>
          ))}
        </ol>
      </nav>

      <div className="flex items-center gap-3">
        <button
          onClick={toggle}
          className="p-2 rounded-full text-on-secondary-container hover:text-primary hover:bg-surface-container-low transition-colors focus:ring-2 focus:ring-primary-container outline-none"
          title={resolvedTheme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
          aria-label={resolvedTheme === "dark" ? "Switch to light mode" : "Switch to dark mode"}
        >
          <Icon name={resolvedTheme === "dark" ? "light_mode" : "dark_mode"} />
        </button>
        <button
          onClick={() => setStatusOpen(true)}
          className="p-2 rounded-full text-on-secondary-container hover:text-primary hover:bg-surface-container-low transition-colors focus:ring-2 focus:ring-primary-container outline-none"
          title="System status"
          aria-label="System status"
        >
          <Icon name="sensors" />
        </button>
        <button
          onClick={() => setNotificationsOpen((value) => !value)}
          className="p-2 rounded-full text-on-secondary-container hover:text-primary hover:bg-surface-container-low transition-colors focus:ring-2 focus:ring-primary-container outline-none relative"
          title="Notifications"
          aria-label="Notifications"
        >
          <Icon name="notifications" />
          {(notifications.data?.unreadCount ?? 0) > 0 && (
            <span className="absolute -top-1 -right-1 min-w-4 h-4 px-1 bg-error text-on-error rounded-full text-[10px] leading-4 text-center">
              {(notifications.data?.unreadCount ?? 0) > 99 ? "99+" : notifications.data?.unreadCount}
            </span>
          )}
        </button>
        {notificationsOpen && (
          <div className="absolute right-24 top-[58px] w-[360px] max-h-[440px] overflow-auto bg-surface-container-lowest border border-border rounded-lg shadow-xl p-3">
            <div className="flex justify-between items-center mb-2"><strong>Notifiche</strong><button onClick={() => markAll.mutate()} className="text-xs text-primary">Segna tutte come lette</button></div>
            {notifications.isError && <p className="text-sm text-error">Impossibile caricare le notifiche.</p>}
            {notifications.data?.items.length === 0 && <p className="text-sm text-on-surface-variant py-4">Nessun avviso operativo.</p>}
            <div className="space-y-1">
              {notifications.data?.items.map((item) => (
                <Link key={item.id} to={item.link ?? "#"} onClick={() => { markRead.mutate(item.id); setNotificationsOpen(false); }} className={`block rounded p-3 hover:bg-surface-container-low ${item.isRead ? "opacity-65" : "bg-surface-container-low"}`}>
                  <div className="flex justify-between gap-2"><span className="text-sm font-semibold">{item.title}</span><span className={item.severity === "error" ? "text-error" : "text-warning"}>●</span></div>
                  <p className="text-xs text-on-surface-variant mt-1">{item.message}</p>
                </Link>
              ))}
            </div>
          </div>
        )}
        <div className="h-4 w-px bg-border mx-1" />
        <Link to="/account" className="flex items-center gap-2 px-3 py-1.5 rounded bg-primary text-on-primary text-label-sm hover:bg-primary-container transition-colors shadow-sm ml-2">
          <span>Account</span>
          <Icon name="person" size={16} />
        </Link>
      </div>
      <Dialog open={statusOpen} onClose={() => setStatusOpen(false)} title="System status">
        <div className="space-y-3">
          <div className="flex justify-between"><span>Stato complessivo</span><strong className="capitalize">{system.data?.status ?? "checking"}</strong></div>
          {system.isError && <p className="text-error text-sm">Impossibile verificare lo stato dei servizi.</p>}
          {system.data?.components.map((component) => <div key={component.name} className="flex justify-between gap-4 border-t border-border pt-2"><div><p className="font-medium">{component.name}</p>{component.message && <p className="text-xs text-on-surface-variant">{component.message}</p>}</div><div className="text-right"><span className="capitalize text-sm">{component.status}</span>{component.latencyMs !== null && <p className="text-xs font-mono">{component.latencyMs} ms</p>}</div></div>)}
          <button onClick={() => system.refetch()} className="text-sm text-primary">Aggiorna stato</button>
        </div>
      </Dialog>
    </header>
  );
}
