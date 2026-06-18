import { createContext, useContext, useState } from "react";
import type { ReactNode } from "react";

export type UserRole = "admin" | "teamlead" | "labic";

export interface User {
  id: number;
  name: string;
  email: string;
  role: UserRole;
  assignedLabs?: string[]; // For Team Lead and Lab IC
  status: "active" | "inactive";
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
const rolePermissions = {
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
    "hierarchy:view",
    "hierarchy:create",
    "hierarchy:edit",
    "category:view",
    "category:create",
    "category:edit",
  ],

  teamlead: [
    "dashboard:view",
    "upload:create",
    "review:view",
    "records:view",
    "reports:view",
    "alerts:view",
    "budget:view",
    "hierarchy:view",
    "category:view",
  ],

  labic: [
    "dashboard:view",
    "upload:create",
    "records:view",
    "reports:view",
    "budget:view",
  ],
};

interface AuthContextType {
  user: User | null;
  isAuthenticated: boolean;
  isLoading: boolean;

  login: (email: string, password: string) => Promise<void>;

  logout: () => void;

  hasRole: (roles: UserRole[]) => boolean;

  hasPermission: (permission: Permission) => boolean;

  canAccessLab: (labCode: string) => boolean;
}

const AuthContext = createContext<AuthContextType | undefined>(undefined);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(() => {
    const stored = localStorage.getItem("user");

    return stored ? JSON.parse(stored) : null;
  });

  const login = async (email: string, password: string) => {
    const response = await authApi.login(email, password);

    setUser(response.user);

    localStorage.setItem("user", JSON.stringify(response.user));

    localStorage.setItem("token", response.token);
  };

  const logout = () => {
    setUser(null);

    localStorage.removeItem("user");

    localStorage.removeItem("token");
  };
  const hasRole = (roles: UserRole[]) => {
    if (!user) {
      return false;
    }

    return roles.includes(user.role);
  };
  const hasAccess = (requiredRoles: UserRole[]) => {
    if (!user) return false;
    return requiredRoles.includes(user.role);
  };
  const hasPermission = (permission: Permission) => {
    if (!user) {
      return false;
    }

    return rolePermissions[user.role].includes(permission);
  };
  return (
    <AuthContext.Provider
      value={{ user, login, logout, hasAccess, hasPermission }}
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

