import { Navigate, Outlet, useLocation } from "react-router-dom";
import { useAuth } from "@/context/AuthContext";

// Gate for every authenticated route: while we're still resolving the
// session (page reload case) we render nothing rather than redirecting, to
// avoid a flash to /login for users who are actually still authenticated.
export default function ProtectedRoute() {
  const { user, isInitializing, requiresTwoFactorSetup } = useAuth();
  const location = useLocation();

  if (isInitializing) return null;

  if (!user) {
    return <Navigate to="/login" state={{ from: location }} replace />;
  }

  // Quando la policy globale lo richiede, ogni account non ancora iscritto
  // viene confinato al setup (stesso controllo applicato dal backend).
  if (requiresTwoFactorSetup && location.pathname !== "/2fa-setup") {
    return <Navigate to="/2fa-setup" replace />;
  }

  return <Outlet />;
}
