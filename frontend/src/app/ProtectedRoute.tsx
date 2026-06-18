import { Navigate } from "react-router";
import { useAuth } from "../context/AuthContext";
import type { UserRole } from "../context/AuthContext";
import type { Permission } from "../context/AuthContext";

interface ProtectedRouteProps {
  children: React.ReactNode;
  allowedRoles?: UserRole[];
  requiredPermissions?: Permission[];
}

export function ProtectedRoute({
  children,
  allowedRoles,
  requiredPermissions,
}: ProtectedRouteProps) {
  const {
    user,
    isLoading,
    hasPermission,
  } = useAuth();

  // Waiting for auth restoration
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen">
        Loading...
      </div>
    );
  }

  // Not authenticated
  if (!user) {
    return (
      <Navigate
        to="/login"
        replace
      />
    );
  }

  // Disabled account
  if (user.status === "inactive") {
    return (
      <Navigate
        to="/login"
        replace
      />
    );
  }

  // Role validation
  if (
    allowedRoles &&
    !allowedRoles.includes(user.role)
  ) {
    return (
      <Navigate
        to="/403"
        replace
      />
    );
  }

  // Permission validation
  if (
    requiredPermissions &&
    !requiredPermissions.every(
      hasPermission
    )
  ) {
    return (
      <Navigate
        to="/403"
        replace
      />
    );
  }

  return <>{children}</>;
}