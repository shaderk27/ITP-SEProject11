import { Navigate } from "react-router";
import { useAuth } from "../context/AuthContext";
import type { UserRole } from "../context/AuthContext";
import type { Permission } from "../context/AuthContext";

interface RouteGuardProps {
  children: React.ReactNode;
  allowedRoles?: UserRole[];
  requiredPermissions?: Permission[];
}

export function RouteGuard({
  children,
  allowedRoles,
  requiredPermissions,
}: RouteGuardProps) {

  const {
    user,
    isLoading,
    hasPermission,
  } = useAuth();

  // Wait for auth restoration
  if (isLoading) {
    return <div>Loading...</div>;
  }

  // Not logged in
  if (!user) {
    return (
      <Navigate
        to="/login"
        replace
      />
    );
  }

  // Inactive account
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
        to="/"
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
        to="/"
        replace
      />
    );
  }

  return <>{children}</>;
}