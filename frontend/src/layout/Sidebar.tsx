import { NavLink } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";
import Icon from "@/components/ui/Icon";
import { cn } from "@/lib/cn";

const NAV_ITEMS = [
  { to: "/dashboard", label: "Dashboard", icon: "dashboard" },
  { to: "/search", label: "Search", icon: "search" },
  { to: "/records", label: "Records", icon: "database" },
  { to: "/sources", label: "Sources", icon: "source" },
  { to: "/exports", label: "Exports", icon: "cloud_download" },
  { to: "/admin", label: "Admin", icon: "settings" },
];

// Persistent left navigation (fixed width per DESIGN.md sidebar-width token).
// Highlights the active section using NavLink's isActive state.
export default function Sidebar() {
  const { logout } = useAuth();

  return (
    <nav className="fixed left-0 top-0 h-screen w-sidebar-width bg-surface-container-lowest border-r border-border flex flex-col py-4 z-50 shadow-[0_0_15px_rgba(0,0,0,0.02)]">
      <div className="px-6 mb-8">
        <h1 className="text-headline-sm text-primary tracking-tight font-semibold">Lavoro Esterno</h1>
        <p className="text-label-sm text-on-surface-variant mt-1">Enterprise Data</p>
      </div>

      <ul className="flex-1 px-4 space-y-1">
        {NAV_ITEMS.map((item) => (
          <li key={item.to}>
            <NavLink
              to={item.to}
              className={({ isActive }) =>
                cn(
                  "flex items-center gap-3 px-4 py-2 rounded transition-colors duration-150",
                  isActive
                    ? "bg-secondary-container text-on-secondary-container font-semibold"
                    : "text-on-surface-variant hover:text-on-surface hover:bg-surface-container-low",
                )
              }
            >
              <Icon name={item.icon} className="text-xl" />
              <span className="text-body-md">{item.label}</span>
            </NavLink>
          </li>
        ))}
      </ul>

      <ul className="px-4 mt-auto space-y-1">
        <li>
          <NavLink
            to="/admin?tab=profile"
            className="flex items-center gap-3 px-4 py-2 rounded text-on-surface-variant hover:text-on-surface hover:bg-surface-container-low transition-colors duration-150"
          >
            <Icon name="account_circle" className="text-xl" />
            <span className="text-body-md">Profile</span>
          </NavLink>
        </li>
        <li>
          <button
            onClick={() => logout()}
            className="w-full flex items-center gap-3 px-4 py-2 rounded text-on-surface-variant hover:text-on-surface hover:bg-surface-container-low transition-colors duration-150"
          >
            <Icon name="logout" className="text-xl" />
            <span className="text-body-md">Logout</span>
          </button>
        </li>
      </ul>
    </nav>
  );
}
