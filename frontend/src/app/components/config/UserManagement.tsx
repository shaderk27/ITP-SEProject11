import { useCallback, useEffect, useState } from "react";
import { useNavigate } from "react-router";
import { Plus, Trash2, Unlink, KeyRound, UserCheck } from "lucide-react";
import { Button } from "../ui/button";
import { Card } from "../ui/card";
import { StatusBadge } from "../shared/StatusBadge";

interface UserData {
  id: number;
  full_name: string;
  email: string;
  staff_id: string | null;
  role: "admin" | "teamlead" | "labic";
  lab_group_name: string | null;
  lab_group_code: string | null;
  lab_assignments?: any[];
  is_active: boolean;
}

const API = import.meta.env.VITE_API_URL ?? "/api";
const API_BASE_URL = import.meta.env.VITE_API_BASE_URL ?? "";

interface UserManagementProps {
  onUsersChanged?: () => void;
  labs?: any[];
}

export function UserManagement({ onUsersChanged, labs: propLabs }: UserManagementProps) {
  const navigate = useNavigate();
  const [users, setUsers] = useState<UserData[]>([]);
  const [labs, setLabs] = useState<any[]>(propLabs || []);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (propLabs) {
      setLabs(propLabs);
    }
  }, [propLabs]);

  const loadUsers = useCallback(() => {
    Promise.all([
      fetch(`${API}/auth/users`, { credentials: "include" }).then((res) => {
        if (!res.ok) throw new Error("Failed to load users.");
        return res.json();
      }),
      propLabs ? Promise.resolve(propLabs) : fetch(`${API_BASE_URL}/api/config/labs`, { credentials: "include" }).then((res) => res.json()).catch(() => [])
    ])
      .then(([userData, labsData]) => {
        setError(null);
        setUsers(userData);
        if (!propLabs && Array.isArray(labsData)) {
          setLabs(labsData);
        }
      })
      .catch((err: unknown) => {
        setError(err instanceof Error ? err.message : "Failed to load users.");
      })
      .finally(() => setIsLoading(false));
  }, [propLabs]);

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
      if (user.lab_assignments && user.lab_assignments.length > 0) {
        return (
          <div className="flex flex-col gap-1.5">
            {user.lab_assignments.map((assignment: any, index: number) => {
              const labId = assignment.lab_id ?? assignment.id;
              const matchingLab = labs.find((l) => l.id === labId);

              const labName =
                matchingLab?.name ||
                matchingLab?.lab_name ||
                assignment.lab_name ||
                assignment.name ||
                "Lab";

              const labCode =
                matchingLab?.code ||
                matchingLab?.lab_code ||
                assignment.lab_code ||
                assignment.code ||
                "";

              const isPrimary = assignment.is_primary ?? false;

              return (
                <div
                  key={labId ?? index}
                  className="flex items-center gap-2 text-sm text-muted-foreground"
                >
                  <span>
                    {labName} {labCode ? `(${labCode})` : ""}
                  </span>
                  <span
                    className={`px-1.5 py-0.5 text-[10px] font-semibold rounded ${
                      isPrimary
                        ? "bg-blue-100 text-blue-800"
                        : "bg-gray-100 text-gray-700"
                    }`}
                  >
                    {isPrimary ? "Primary" : "Secondary"}
                  </span>
                </div>
              );
            })}
          </div>
        );
      }
      return "Unassigned lab";
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

  const hasScope = (user: UserData) => {
    if (user.role === "teamlead") return Boolean(user.lab_group_name);
    if (user.role === "labic")
      return Boolean(user.lab_assignments && user.lab_assignments.length > 0);
    return Boolean(
      user.lab_group_name ||
        (user.lab_assignments && user.lab_assignments.length > 0),
    );
  };

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
    const confirmed = window.confirm(
      `Clear all assignments for ${user.full_name}?`,
    );
    if (!confirmed) return;

    try {
      const res = await fetch(`${API}/auth/users/${user.id}/unassign-scope`, {
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
      alert(
        "Unassign this user from their Lab or Lab Group before deactivating the account.",
      );
      return;
    }

    const confirmed = window.confirm(`Deactivate ${user.full_name}?`);
    if (!confirmed) return;

    try {
      const res = await fetch(`${API}/auth/users/${user.id}/deactivate`, {
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

  const handleActivateUser = async (user: UserData) => {
    if (user.is_active) return;

    const confirmed = window.confirm(`Reactivate ${user.full_name}?`);
    if (!confirmed) return;

    try {
      const res = await fetch(`${API}/auth/users/${user.id}/activate`, {
        method: "PUT",
        credentials: "include",
      });
      if (!res.ok) {
        alert(await readErrorDetail(res, "Failed to activate user."));
        return;
      }
      loadUsers();
      onUsersChanged?.();
    } catch {
      alert("Failed to activate user.");
    }
  };

  const [resetTargetUser, setResetTargetUser] = useState<UserData | null>(null);
  const [isResetting, setIsResetting] = useState(false);
  const [resetSuccess, setResetSuccess] = useState<string | null>(null);
  const [resetError, setResetError] = useState<string | null>(null);

  const handleAdminResetPassword = async () => {
    if (!resetTargetUser) return;
    setIsResetting(true);
    setResetSuccess(null);
    setResetError(null);

    try {
      const res = await fetch(
        `${API}/auth/users/${resetTargetUser.id}/send-reset`,
        {
          method: "POST",
          credentials: "include",
        },
      );
      if (res.ok) {
        setResetSuccess(
          `A temporary password has been sent to ${resetTargetUser.email}.`,
        );
      } else {
        const msg = await readErrorDetail(res, "Failed to send reset email.");
        setResetError(msg);
      }
    } catch {
      setResetError("Network error. Please try again.");
    } finally {
      setIsResetting(false);
    }
  };

  if (isLoading) {
    return (
      <div className="p-6 text-sm text-muted-foreground">Loading users...</div>
    );
  }

  return (
    <Card className="bg-white border-border">
      <div className="p-6 border-b border-border flex items-center justify-between">
        <div>
          <h3 className="text-lg font-semibold text-foreground">
            User Management
          </h3>
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
        <div className="m-6 rounded-md border border-destructive/25 bg-destructive/10 px-4 py-3 text-sm text-destructive">
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
                Staff ID
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
                <td className="p-4 text-sm text-muted-foreground">
                  {user.staff_id ?? (
                    <span className="text-gray-300 italic">—</span>
                  )}
                </td>
                <td className="p-4 text-sm text-muted-foreground">
                  {user.email}
                </td>
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
                  <StatusBadge
                    status={user.is_active ? "approved" : "rejected"}
                  >
                    {user.is_active ? "Active" : "Inactive"}
                  </StatusBadge>
                </td>
                <td className="p-4 text-center">
                  <div className="flex items-center justify-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      disabled={!user.is_active || user.role === "admin"}
                      title={
                        user.role === "admin"
                          ? "Admin passwords cannot be reset by another admin"
                          : user.is_active
                            ? "Send password reset email"
                            : "User is inactive"
                      }
                      onClick={() => {
                        setResetTargetUser(user);
                        setResetSuccess(null);
                        setResetError(null);
                      }}
                    >
                      <KeyRound className="h-3 w-3" />
                    </Button>
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
                    {user.is_active ? (
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-[#dc2626] hover:text-[#dc2626]"
                        title={
                          hasScope(user)
                            ? "Unassign user before deactivation"
                            : "Deactivate user"
                        }
                        onClick={() => handleDeactivateUser(user)}
                      >
                        <Trash2 className="h-3 w-3" />
                      </Button>
                    ) : (
                      <Button
                        size="sm"
                        variant="outline"
                        className="text-[#16a34a] hover:text-[#16a34a]"
                        title="Activate user"
                        onClick={() => handleActivateUser(user)}
                      >
                        <UserCheck className="h-3 w-3" />
                      </Button>
                    )}
                  </div>
                </td>
              </tr>
            ))}
            {users.length === 0 && !error && (
              <tr>
                <td
                  colSpan={7}
                  className="p-6 text-center text-sm text-muted-foreground"
                >
                  No users found.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>

      {resetTargetUser && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 backdrop-blur-sm px-4">
          <div className="bg-white w-full max-w-md rounded-xl shadow-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-gray-50/50">
              <h3 className="text-lg font-semibold text-gray-800">
                Reset Password
              </h3>
              <button
                onClick={() => setResetTargetUser(null)}
                className="text-gray-400 hover:text-gray-600 hover:bg-gray-100 p-1.5 rounded-md transition-colors"
              >
                ✕
              </button>
            </div>

            <div className="p-6 space-y-4">
              {resetSuccess ? (
                <div className="p-3 text-sm text-green-700 bg-green-50 border border-green-100 rounded-lg">
                  {resetSuccess}
                </div>
              ) : (
                <p className="text-sm text-gray-600">
                  This will send a temporary password to{" "}
                  <span className="font-medium text-gray-800">
                    {resetTargetUser.email}
                  </span>
                  . The temporary password expires in 1 hour.
                </p>
              )}

              {resetError && (
                <div className="p-3 text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg">
                  {resetError}
                </div>
              )}

              <div className="flex justify-end gap-3 pt-2">
                <button
                  onClick={() => setResetTargetUser(null)}
                  className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  {resetSuccess ? "Close" : "Cancel"}
                </button>
                {!resetSuccess && (
                  <button
                    onClick={handleAdminResetPassword}
                    disabled={isResetting}
                    className="px-4 py-2 text-sm font-medium text-white bg-[#1e3a8a] rounded-lg hover:bg-[#1e40af] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {isResetting ? "Sending..." : "Send Temporary Password"}
                  </button>
                )}
              </div>
            </div>
          </div>
        </div>
      )}
    </Card>
  );
}