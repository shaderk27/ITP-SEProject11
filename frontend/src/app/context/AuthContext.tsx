import { createContext, useContext, useState, useEffect } from "react";
import type { ReactNode } from "react";

export type UserRole = "admin" | "teamlead" | "labic";

export interface User {
  // Field names match what the backend returns from the DB:
  // users.user_id, users.full_name, users.email, roles.role_name, users.lab_group_id
  id: number;
  fullName: string;
  email: string;
  role: UserRole;
  labGroupId: number | null; // null for admin — no lab group restriction
}

export type Permission =
  | "dashboard:view"
  | "upload:create"
  | "review:view"
  | "review:approve"
  | "records:view"
  | "reports:view"
  | "alerts:view"
  | "audit:view"
  | "config:view"
  | "config:edit"
  | "budget:view"
  | "budget:edit"
  | "hierarchy:view"
  | "hierarchy:create"
  | "hierarchy:edit"
  | "category:view"
  | "category:create"
  | "category:edit";

const rolePermissions: Record<UserRole, Permission[]> = {
  admin: [
    "dashboard:view", "upload:create", "review:view", "review:approve",
    "records:view", "reports:view", "alerts:view", "audit:view",
    "config:view", "config:edit", "budget:view", "budget:edit",
  ],
  teamlead: [
    "dashboard:view", "upload:create", "review:view", "records:view",
    "reports:view", "alerts:view", "budget:view",
  ],
  labic: [
    "dashboard:view", "records:view", "reports:view", "budget:view",
  ],
};

interface AuthContextType {
  user: User | null;
  // isLoading is true until the /me session restore resolves on mount.
  // ProtectedRoute must check this before making any redirect decisions.
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  hasAccess: (requiredRoles: UserRole[]) => boolean;
  hasPermission: (permission: Permission) => boolean;
  canAccessLabGroup: (labGroupId: number) => boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8000";

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // On mount, call /me to restore session from the httpOnly cookie.
  // localStorage is intentionally not used — the cookie is the source of truth.
  useEffect(() => {
    fetch(`${API}/api/auth/me`, { credentials: "include" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => setUser(data))
      .catch(() => setUser(null))
      .finally(() => setIsLoading(false));
  }, []);

  const login = async (email: string, password: string) => {
    const res = await fetch(`${API}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include", // allows Set-Cookie from the backend to be stored
      body: JSON.stringify({ email, password }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "Login failed");
    }

    const userData: User = await res.json();
    setUser(userData);
  };

  const logout = async () => {
    // Tell the backend to invalidate the session before clearing local state
    await fetch(`${API}/api/auth/logout`, {
      method: "POST",
      credentials: "include",
    });
    setUser(null);
  };

  const hasAccess = (requiredRoles: UserRole[]) => {
    if (!user) return false;
    return requiredRoles.includes(user.role);
  };

  const hasPermission = (permission: Permission) => {
    if (!user) return false;
    return rolePermissions[user.role].includes(permission);
  };

  // Lab group access: admins see everything; others are scoped to their lab_group_id.
  // canAccessLabGroup replaces the old canAccessLab(labCode) — the schema uses
  // lab_group_id as the foreign key on users, not an array of lab code strings.
  const canAccessLabGroup = (labGroupId: number) => {
    if (!user) return false;
    if (user.role === "admin") return true;
    return user.labGroupId === labGroupId;
  };

  return (
    <AuthContext.Provider
      value={{ user, isLoading, login, logout, hasAccess, hasPermission, canAccessLabGroup }}
    >
      {children}
    </AuthContext.Provider>
  );
}

// eslint-disable-next-line react-refresh/only-export-components
export function useAuth() {
  const context = useContext(AuthContext);
  if (context === undefined) {
    throw new Error("useAuth must be used within an AuthProvider");
  }
  return context;
}
