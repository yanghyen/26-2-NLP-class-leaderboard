"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState
} from "react";

import { api, AUTH_EXPIRED_EVENT } from "../lib/api";
import type { User } from "../lib/types";

const TOKEN_KEY = "nlp-admin-token";

interface AuthValue {
  user: User | null;
  token: string | null;
  loading: boolean;
  login: (loginId: string, password: string) => Promise<User>;
  logout: () => void;
}

const AuthContext = createContext<AuthValue | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const router = useRouter();
  const [token, setToken] = useState<string | null>(null);
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState(true);

  const logout = useCallback(() => {
    sessionStorage.removeItem(TOKEN_KEY);
    setToken(null);
    setUser(null);
    router.replace("/login");
  }, [router]);

  useEffect(() => {
    const saved = sessionStorage.getItem(TOKEN_KEY);
    if (!saved) {
      setLoading(false);
      return;
    }
    setToken(saved);
    api.me(saved)
      .then((current) => { if (current.role !== "ADMIN") throw new Error("관리자 계정이 필요합니다."); setUser(current); })
      .catch(() => {
        sessionStorage.removeItem(TOKEN_KEY);
        setToken(null);
      })
      .finally(() => setLoading(false));
  }, []);

  useEffect(() => {
    window.addEventListener(AUTH_EXPIRED_EVENT, logout);
    return () => window.removeEventListener(AUTH_EXPIRED_EVENT, logout);
  }, [logout]);

  const login = useCallback(async (loginId: string, password: string) => {
    const result = await api.login(loginId, password);
    const current = await api.me(result.access_token);
    if (current.role !== "ADMIN") throw new Error("관리자 계정이 필요합니다.");
    sessionStorage.setItem(TOKEN_KEY, result.access_token);
    setToken(result.access_token);
    setUser(current);
    return current;
  }, []);

  const value = useMemo(
    () => ({ user, token, loading, login, logout }),
    [user, token, loading, login, logout]
  );
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthValue {
  const value = useContext(AuthContext);
  if (!value) throw new Error("useAuth must be used within AuthProvider");
  return value;
}
