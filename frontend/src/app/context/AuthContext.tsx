import { createContext, useContext, useState, useEffect } from "react";
import type { ReactNode } from "react";

export type UserRole = "admin" | "teamlead" | "labic";

export interface User {
  id: number;
  fullName: string;
  email: string;
  role: UserRole;
  assignedLabs: string[]; 
  labGroupId: number | null; 
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
  isLoading: boolean;
  login: (email: string, password: string) => Promise<void>;
  logout: () => Promise<void>;
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
    return rawLabs.split(",").map((l) => l.trim()).filter(Boolean);
  }
  return [];
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [isLoading, setIsLoading] = useState(true);

  // 1. Session Restore on Mount
  useEffect(() => {
    fetch(`${API}/api/auth/me`, { credentials: "include" })
      .then((res) => (res.ok ? res.json() : null))
      .then((data) => {
        if (data) {
          const rawWbsCode = data.lab_group?.wbs_code || data.wbs_code;

          // Normalize backend properties to frontend camelCase matches
          setUser({
            id: data.id,
            fullName: data.full_name,
            email: data.email,
            role: data.role,
            labGroupId: data.lab_group_id,
            assignedLabs: parseAssignedLabs(rawWbsCode), //  FIXED: Parsed from the wbs_code column link
          });
        } else {
          setUser(null);
        }
      })
      .catch(() => setUser(null))
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
    
    const rawWbsCode = rawUser.wbs_code || rawUser.lab_group?.wbs_code || rawUser.assigned_labs;

    setUser({
      id: rawUser.id,
      fullName: rawUser.full_name,
      email: rawUser.email,
      role: rawUser.role,
      labGroupId: rawUser.lab_group_id,
      assignedLabs: parseAssignedLabs(rawWbsCode), //  FIXED: Sync with login endpoint
    });
  };

  // 3. Functional Logout Handler
  const logout = async () => {
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
  };

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