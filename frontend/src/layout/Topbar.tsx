import { Link, useLocation } from "react-router-dom";
import Icon from "@/components/ui/Icon";

const SEGMENT_LABELS: Record<string, string> = {
  dashboard: "Dashboard",
  search: "Search",
  records: "Records",
  sources: "Sources",
  exports: "Exports",
  admin: "Admin",
  overview: "Overview",
  occurrences: "Occurrences",
  media: "Media",
  "ai-summary": "AI Summary",
  history: "History",
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
          className="p-2 rounded-full text-on-secondary-container hover:text-primary hover:bg-surface-container-low transition-colors focus:ring-2 focus:ring-primary-container outline-none"
          title="System status"
        >
          <Icon name="sensors" />
        </button>
        <button
          className="p-2 rounded-full text-on-secondary-container hover:text-primary hover:bg-surface-container-low transition-colors focus:ring-2 focus:ring-primary-container outline-none relative"
          title="Notifications"
        >
          <Icon name="notifications" />
          <span className="absolute top-1 right-1 w-2 h-2 bg-error rounded-full" />
        </button>
        <div className="h-4 w-px bg-border mx-1" />
        <a
          href="mailto:support@lavoro.internal"
          className="text-label-sm text-on-surface-variant hover:text-primary px-2 py-1 rounded transition-colors"
        >
          Support
        </a>
        <button className="flex items-center gap-2 px-3 py-1.5 rounded bg-primary text-on-primary text-label-sm hover:bg-primary-container transition-colors shadow-sm ml-2">
          <span>Account</span>
          <Icon name="person" size={16} />
        </button>
      </div>
    </header>
  );
}
