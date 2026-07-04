import { createContext, useContext, useState, useEffect, useCallback } from "react";
import type { ReactNode } from "react";
import { SessionTimeoutProvider } from "./SessionTimeoutProvider";

export type UserRole = "admin" | "teamlead" | "labic";

export interface User {
  id: number;
  fullName: string;
  email: string;
  role: UserRole;
  assignedLabs: string[];
  labGroupId: number | null;
  mustResetPassword: boolean;
}

export type Permission =
  | "user:create"
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
    "dashboard:view",
    "upload:create",
    "review:view",
    "review:approve",
    "records:view",
    "reports:view",
    "alerts:view",
    "audit:view",
    "config:view",
    "config:edit",
    "budget:view",
    "budget:edit",
    "user:create",
  ],
  teamlead: [
    "dashboard:view",
    "upload:create",
    "review:view",
    "records:view",
    "reports:view",
    "alerts:view",
    "budget:view",
  ],
  labic: ["dashboard:view", "records:view", "reports:view", "budget:view"],
};

interface AuthContextType {
  user: User | null;
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
  updateUser: (updates: Partial<User>) => void;
  clearResetFlag: () => void;
  hasAccess: (requiredRoles: UserRole[]) => boolean;
  hasPermission: (permission: Permission) => boolean;
  canAccessLabGroup: (labGroupId: number) => boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8080";

// Helper function to safely parse backend lab strings/arrays into standard array structures
function parseAssignedLabs(rawLabs: any): string[] {
  if (!rawLabs) return [];
  if (Array.isArray(rawLabs)) return rawLabs;
  if (typeof rawLabs === "string") {
    return rawLabs
      .split(",")
      .map((l) => l.trim())
      .filter(Boolean);
  }
  return [];
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const updateUser = (updates: Partial<User>) => {
    setUser((prev) => (prev ? { ...prev, ...updates } : null));
  };
  const clearResetFlag = () => {
    setUser((prev) => (prev ? { ...prev, mustResetPassword: false } : null));
  };

  // 1. Session Restore on Mount
  useEffect(() => {
    fetch(`${API}/api/auth/me`, { credentials: "include" })
      .then(async (res) => {
        if (res.status === 403) {
          // May be a temp-reset session
          const fallback = await fetch(`${API}/api/auth/me/reset`, {
            credentials: "include",
          });
          if (fallback.ok) {
            const data = await fallback.json();
            if (data.must_reset_password) {
              setUser({
                id: data.id,
                fullName: "",
                email: "",
                role: "labic",
                labGroupId: null,
                assignedLabs: [],
                mustResetPassword: true,
              });
            }
          } else {
            setUser(null);
          }
          return null;
        }
        return res.ok ? res.json() : null;
      })
      .then((data) => {
        if (!data) return;
        const rawAssignedLabs =
          data.assignedLabs ||
          data.assigned_labs ||
          data.lab_group?.wbs_code ||
          data.wbs_code;

        setUser({
          id: data.id,
          fullName: data.full_name,
          email: data.email,
          role: data.role,
          labGroupId: data.lab_group_id,
          assignedLabs: parseAssignedLabs(rawAssignedLabs),
          mustResetPassword: data.must_reset_password ?? false,
        });
      })
      .finally(() => setIsLoading(false));
  }, []);

  // Make sure to mirror this exact change inside your login function block too:
  const login = async (email: string, password: string) => {
    const res = await fetch(`${API}/api/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      credentials: "include",
      body: JSON.stringify({ email, password }),
    });

    if (!res.ok) {
      const err = await res.json().catch(() => ({}));
      throw new Error(err.detail ?? "Login failed");
    }

    const rawJson = await res.json();
    const rawUser = rawJson.user;
    const rawAssignedLabs =
      rawUser.assignedLabs ||
      rawUser.assigned_labs ||
      rawUser.wbs_code ||
      rawUser.lab_group?.wbs_code;

    setUser({
      id: rawUser.id,
      fullName: rawUser.full_name,
      email: rawUser.email,
      role: rawUser.role,
      labGroupId: rawUser.lab_group_id,
      assignedLabs: parseAssignedLabs(rawAssignedLabs),
      mustResetPassword: rawUser.must_reset_password ?? false,
    });
  };

  // 3. Functional Logout Handler
  const logout = useCallback(async () => {
    try {
      await fetch(`${API}/api/auth/logout`, {
        method: "POST",
        credentials: "include",
      });
    } catch (error) {
      console.error("Backend logout handshaking encountered an issue:", error);
    } finally {
      setUser(null);
    }
  }, []);

  const hasAccess = (requiredRoles: UserRole[]) => {
    if (!user) return false;
    return requiredRoles.includes(user.role);
  };

  const hasPermission = (permission: Permission) => {
    if (!user) return false;
    return rolePermissions[user.role].includes(permission);
  };

  const canAccessLabGroup = (labGroupId: number) => {
    if (!user) return false;
    if (user.role === "admin") return true;
    return user.labGroupId === labGroupId;
  };

  return (
    <AuthContext.Provider
      value={{
        user,
        isLoading,
        login,
        logout,
        updateUser,
        clearResetFlag,
        hasAccess,
        hasPermission,
        canAccessLabGroup,
      }}
    >
      <SessionTimeoutProvider isAuthenticated={!!user} logout={logout}>
        {children}
      </SessionTimeoutProvider>
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
