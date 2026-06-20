import { Navigate } from "react-router";
import { useAuth } from "../context/AuthContext";
import type { UserRole, Permission } from "../context/AuthContext";

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
  const { user, hasPermission } = useAuth();

  // Not authenticated — send to login
  if (!user) {
    return <Navigate to="/login" replace />;
  }

  // Disabled account — send to a dedicated page, not login,
  // so the user understands why they can't get in.
  if (user.status === "inactive") {
    return (
      <Navigate
        to="/login"
        replace
        state={{ reason: "inactive" }}
      />
    );
  }

  // Role check — fails if the user's role isn't in the allowedRoles list.
  // Only evaluated when allowedRoles is explicitly provided.
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/403" replace />;
  }

  // Permission check — all listed permissions must be satisfied (AND logic).
  // Only evaluated when requiredPermissions is explicitly provided.
  if (
    requiredPermissions &&
    !requiredPermissions.every(hasPermission)
  ) {
    return <Navigate to="/403" replace />;
  }

  return <>{children}</>;
}
