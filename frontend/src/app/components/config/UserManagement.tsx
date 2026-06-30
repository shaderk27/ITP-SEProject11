import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { Plus, Trash2, Unlink } from "lucide-react";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
import { StatusBadge } from "../shared/StatusBadge";

interface UserData {
  id: number;
  full_name: string;
  email: string;
  role: "admin" | "teamlead" | "labic";
  lab_group_name: string | null;
  lab_group_code: string | null;
  lab_name: string | null;
  lab_code: string | null;
  is_active: boolean;
}

const API = import.meta.env.VITE_API_URL ?? "http://localhost:8080";

interface UserManagementProps {
  onUsersChanged?: () => void;
}

export function UserManagement({ onUsersChanged }: UserManagementProps) {
  const navigate = useNavigate();
  const [users, setUsers] = useState<UserData[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const loadUsers = useCallback(() => {
    fetch(`${API}/api/auth/users`, { credentials: "include" })
      .then((res) => {
        if (!res.ok) throw new Error("Failed to load users.");
        return res.json();
      })
      .then((data) => {
        setError(null);
        setUsers(data);
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load users.");
      })
      .finally(() => setIsLoading(false));
  }, []);

  useEffect(() => {
    loadUsers();
  }, [loadUsers]);

  const getScopeLabel = (user: UserData) => {
    if (user.role === "teamlead") {
      return user.lab_group_name
        ? `${user.lab_group_name}${user.lab_group_code ? ` - ${user.lab_group_code}` : ""}`
        : "Unassigned lab group";
    }
    if (user.role === "labic") {
      return user.lab_name
        ? `${user.lab_name}${user.lab_code ? ` - ${user.lab_code}` : ""}`
        : "Unassigned lab";
    }
    return "-";
  };

  const getRoleBadgeStatus = (role: string) => {
    switch (role) {
      case "admin":
        return "override";
      case "teamlead":
        return "healthy";
      case "labic":
        return "info";
      default:
        return "general";
    }
  };

  const hasScope = (user: UserData) => Boolean(user.lab_group_name || user.lab_name);

  const readErrorDetail = async (res: Response, fallback: string) => {
    try {
      const body = await res.json();
      return typeof body?.detail === "string" ? body.detail : fallback;
    } catch {
      return fallback;
    }
  };

  const handleUnassignScope = async (user: UserData) => {
    if (!hasScope(user)) return;
    const confirmed = window.confirm(`Clear assignment for ${user.full_name}?`);
    if (!confirmed) return;

    try {
      const res = await fetch(`${API}/api/auth/users/${user.id}/unassign-scope`, {
        method: "PUT",
        credentials: "include",
      });
      if (!res.ok) {
        alert(await readErrorDetail(res, "Failed to clear assignment."));
        return;
      }
      loadUsers();
      onUsersChanged?.();
    } catch {
      alert("Failed to clear assignment.");
    }
  };

  const handleDeactivateUser = async (user: UserData) => {
    if (!user.is_active) return;
    if (hasScope(user)) {
      alert("Unassign this user from their Lab or Lab Group before deactivating the account.");
      return;
    }

    const confirmed = window.confirm(`Deactivate ${user.full_name}?`);
    if (!confirmed) return;

    try {
      const res = await fetch(`${API}/api/auth/users/${user.id}/deactivate`, {
        method: "PUT",
        credentials: "include",
      });
      if (!res.ok) {
        alert(await readErrorDetail(res, "Failed to deactivate user."));
        return;
      }
      loadUsers();
      onUsersChanged?.();
    } catch {
      alert("Failed to deactivate user.");
    }
  };

  if (isLoading) {
    return <div className="p-6 text-sm text-muted-foreground">Loading users...</div>;
  }

  return (
    <Card className="bg-white border-border">
      <div className="p-6 border-b border-border flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-foreground">User Management</h3>
          <p className="text-sm text-muted-foreground mt-1">
            View users and their assigned role scope
          </p>
        </div>
        <Button
          className="bg-[#1e3a8a] hover:bg-[#1e40af] text-white"
          onClick={() => navigate("/users/create")}
        >
          <Plus className="h-4 w-4 mr-2" />
          Create User
        </Button>
      </div>

      {error && (
        <div className="m-6 rounded-md border border-destructive/20 bg-destructive/10 px-4 py-3 text-sm text-destructive">
          {error}
        </div>
      )}

      <div className="overflow-x-auto">
        <table className="w-full">
          <thead className="bg-[#f8f9fa]">
            <tr className="border-b border-border">
              <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                Name
              </th>
              <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                Email
              </th>
              <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                Role
              </th>
              <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                Scope
              </th>
              <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                Status
              </th>
              <th className="text-center p-4 text-sm font-medium text-muted-foreground">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {users.map((user) => (
              <tr
                key={user.id}
                className="border-b border-border last:border-0 hover:bg-[#f8f9fa]"
              >
                <td className="p-4 text-sm font-medium text-foreground">
                  {user.full_name}
                </td>
                <td className="p-4 text-sm text-muted-foreground">{user.email}</td>
                <td className="p-4">
                  <StatusBadge status={getRoleBadgeStatus(user.role) as any}>
                    {user.role === "teamlead"
                      ? "Team Lead"
                      : user.role === "labic"
                        ? "Lab IC"
                        : "Admin"}
                  </StatusBadge>
                </td>
                <td className="p-4 text-sm text-muted-foreground">
                  {getScopeLabel(user)}
                </td>
                <td className="p-4">
                  <StatusBadge status={user.is_active ? "approved" : "rejected"}>
                    {user.is_active ? "Active" : "Inactive"}
                  </StatusBadge>
                </td>
                <td className="p-4 text-center">
                  <div className="flex items-center justify-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!user.is_active || !hasScope(user)}
                      title={
                        user.is_active && hasScope(user)
                          ? "Clear lab or lab group assignment"
                          : "No assignment to clear"
                      }
                      onClick={() => handleUnassignScope(user)}
                    >
                      <Unlink className="h-3 w-3" />
                    </Button>
                    <Button
                      size="sm"
                      variant="outline"
                      className="text-[#dc2626] hover:text-[#dc2626]"
                      disabled={!user.is_active}
                      title={
                        !user.is_active
                          ? "User is already inactive"
                          : hasScope(user)
                            ? "Unassign user before deactivation"
                            : "Deactivate user"
                      }
                      onClick={() => handleDeactivateUser(user)}
                    >
                      <Trash2 className="h-3 w-3" />
                    </Button>
                  </div>
                </td>
              </tr>
            ))}
            {users.length === 0 && !error && (
              <tr>
                <td colSpan={6} className="p-6 text-center text-sm text-muted-foreground">
                  No users found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
