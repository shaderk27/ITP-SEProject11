import { Navigate, useLocation } from "react-router";
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
  const { user, isLoading, hasPermission } = useAuth();
  const location = useLocation();

  // Wait for the /me session restore before making any redirect decisions.
  // Without this, every page refresh bounces to /login before the cookie
  // check has a chance to complete.
  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-screen text-sm text-muted-foreground">
        Loading...
      </div>
    );
  }

  // Not authenticated: preserve the intended path so login can redirect back.
  if (!user) {
    return (
      <Navigate to="/login" replace state={{ from: location.pathname }} />
    );
  }
  
  if (user.mustResetPassword && location.pathname !== "/reset-password") {
    return <Navigate to="/reset-password" state={{ forced: true }} replace />;
  }
  // Role check only runs when allowedRoles is explicitly provided.
  if (allowedRoles && !allowedRoles.includes(user.role)) {
    return <Navigate to="/403" replace />;
  }

  // Permission check requires all listed permissions to pass.
  if (requiredPermissions && !requiredPermissions.every(hasPermission)) {
    return <Navigate to="/403" replace />;
  }

  return <>{children}</>;
}
