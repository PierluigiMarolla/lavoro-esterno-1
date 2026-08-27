import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from "react";
import * as authApi from "@/api/auth";
import { tokenStorage } from "@/api/client";
import type { LoginResult, User } from "@/types";

interface AuthContextValue {
  user: User | null;
  // True while we're checking for an existing session on first load, so
  // ProtectedRoute can avoid a flash-redirect to /login before we know.
  isInitializing: boolean;
  login: (email: string, password: string) => Promise<LoginResult>;
  verifyTwoFactor: (mfaToken: string, code: string) => Promise<void>;
  logout: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isInitializing, setIsInitializing] = useState(true);

  // On mount, if a refresh token is already in storage, silently resolve the
  // current user so a page reload doesn't bounce an already-logged-in user to /login.
  useEffect(() => {
    const bootstrap = async () => {
      if (!tokenStorage.getAccessToken()) {
        setIsInitializing(false);
        return;
      }
      try {
        const me = await authApi.fetchCurrentUser();
        setUser(me);
      } catch {
        tokenStorage.clear();
      } finally {
        setIsInitializing(false);
      }
    };
    bootstrap();
  }, []);

  // apiRequest fires this event when a refresh attempt fails outright, so
  // the app can react centrally instead of every caller catching 401s.
  useEffect(() => {
    const onSessionExpired = () => setUser(null);
    window.addEventListener("lavoro-esterno:session-expired", onSessionExpired);
    return () => window.removeEventListener("lavoro-esterno:session-expired", onSessionExpired);
  }, []);

  const login = useCallback(async (email: string, password: string) => {
    const result = await authApi.login(email, password);
    if (result.status === "authenticated") {
      tokenStorage.setTokens(result.tokens.accessToken, result.tokens.refreshToken);
      setUser(result.user);
    }
    return result;
  }, []);

  const verifyTwoFactor = useCallback(async (mfaToken: string, code: string) => {
    const result = await authApi.loginWithTwoFactor(mfaToken, code);
    if (result.status === "authenticated") {
      tokenStorage.setTokens(result.tokens.accessToken, result.tokens.refreshToken);
      setUser(result.user);
    }
  }, []);

  const logout = useCallback(async () => {
    try {
      await authApi.logout();
    } finally {
      tokenStorage.clear();
      setUser(null);
    }
  }, []);

  const value = useMemo(
    () => ({ user, isInitializing, login, verifyTwoFactor, logout }),
    [user, isInitializing, login, verifyTwoFactor, logout],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error("useAuth must be used within AuthProvider");
  return ctx;
}
