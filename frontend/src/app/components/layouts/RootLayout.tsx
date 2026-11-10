import { useState, useEffect } from "react";
import { Outlet, Link, useLocation, useNavigate } from "react-router";
import {
  LayoutDashboard,
  Upload,
  ClipboardCheck,
  FileText,
  BarChart3,
  Bell,
  FileSearch,
  Settings,
  MessageSquare,
  LogOut,
  UserPlus,
  X,
  User as UserIcon,
  Lock,
} from "lucide-react";
import type { LucideIcon } from "lucide-react";
import { cn } from "../ui/utils";
import { useAuth } from "../../context/AuthContext";
import type { User, UserRole } from "../../context/AuthContext";
import {
  useSessionTimeout,
  WARNING_BEFORE_EXPIRY_MS,
} from "../../services/useSessionTimeout";
import { FEATURES } from "../../config/features";
import { AskAiWidget } from "../shared/AskAiWidget";

interface NavItem {
  name: string;
  path: string;
  icon: LucideIcon;
  roles: UserRole[];
}

interface AlertLabGroupSummary {
  id: number;
  budget?: number;
  spent?: number;
}

interface AlertLabSummary {
  id: number;
  group_id?: number;
  budget?: number;
  spent?: number;
}

const navigation: NavItem[] = [
  {
    name: "Dashboard",
    path: "/",
    icon: LayoutDashboard,
    roles: ["admin", "teamlead", "labic"],
  },
  {
    name: "Upload",
    path: "/upload",
    icon: Upload,
    roles: ["admin", "teamlead"],
  },
  {
    name: "Review Queue",
    path: "/review",
    icon: ClipboardCheck,
    roles: ["admin", "teamlead"],
  },
  {
    name: "PR Records",
    path: "/records",
    icon: FileText,
    roles: ["admin", "teamlead", "labic"],
  },
  ...(FEATURES.reports
    ? [
        {
          name: "Reports",
          path: "/reports",
          icon: BarChart3,
          roles: ["admin", "teamlead", "labic"] as UserRole[],
        },
      ]
    : []),
  {
    name: "Alerts",
    path: "/alerts",
    icon: Bell,
    roles: ["admin", "teamlead", "labic"],
  },
  ...(FEATURES.auditLog
    ? [
        {
          name: "Audit Log",
          path: "/audit",
          icon: FileSearch,
          roles: ["admin"] as UserRole[],
        },
      ]
    : []),
  {
    name: "Create User",
    path: "/users/create",
    icon: UserPlus,
    roles: ["admin","teamlead"],
  },
  ...(FEATURES.chatbot
    ? [
        {
          name: "AI Chatbot",
          path: "/chatbot",
          icon: MessageSquare,
          roles: ["admin", "teamlead", "labic"] as UserRole[],
        },
      ]
    : []),
  { name: "System Config", path: "/config", icon: Settings, roles: ["admin","teamlead"] },
];

const getThresholdLevel = (util: number): number => {
  if (util >= 100) return 100;
  if (util >= 95) return 95;
  if (util >= 80) return 80;
  if (util >= 50) return 50;
  return 0;
};

/**
 * Builds stable, spend-independent alert identity keys scoped to the user's role:
 *   - `lab:{lab_id}:threshold:{threshold_level}`
 *   - `lab-group:{lab_group_id}:threshold:{threshold_level}`
 */
function buildAlertNotificationKeys(
  labGroups: AlertLabGroupSummary[],
  labs: AlertLabSummary[],
  user: Pick<User, "role" | "labGroupId" | "labIds">,
): string[] {
  const currentKeys: string[] = [];

  const groupsToProcess = labGroups.filter((g) => {
    if (user.role === "admin") return true;
    if (user.role === "teamlead") return g.id === user.labGroupId;
    if (user.role === "labic") {
      return labs.some(
        (lab) => lab.group_id === g.id && user.labIds.includes(lab.id),
      );
    }
    return false;
  });

  groupsToProcess.forEach((group) => {
    const isLabIC = user.role === "labic";
    const groupBudget = Number(group.budget || 0);
    const groupSpent = Number(group.spent || 0);
    const groupUtil =
      !isLabIC && groupBudget > 0 ? (groupSpent / groupBudget) * 100 : 0;
    const groupThreshold = getThresholdLevel(groupUtil);

    let groupLabs = labs.filter(
      (lab) =>
        lab.group_id === group.id &&
        (Number(lab.budget || 0) > 0 || Number(lab.spent || 0) > 0),
    );
    if (isLabIC) {
      groupLabs = groupLabs.filter((lab) => user.labIds.includes(lab.id));
    }

    let anyLabThresholdAdded = false;
    groupLabs.forEach((lab) => {
      const budget = Number(lab.budget || 0);
      const spent = Number(lab.spent || 0);
      const util =
        budget > 0 ? (spent / budget) * 100 : spent > 0 ? 100 : 0;
      const labThreshold = getThresholdLevel(util);

      if (labThreshold > 0) {
        anyLabThresholdAdded = true;
        currentKeys.push(`lab:${lab.id}:threshold:${labThreshold}`);
      }
    });

    if (!isLabIC && groupThreshold > 0 && !anyLabThresholdAdded) {
      currentKeys.push(`lab-group:${group.id}:threshold:${groupThreshold}`);
    }
  });

  return currentKeys;
}

/**
 * Reconciles active alert keys against stored seen keys:
 *  - Prunes seen keys for labs/groups that dropped below their threshold or
 *    escalated to a different threshold so future crossings count as new.
 *  - Returns { unreadCount, nextSeenKeys }.
 */
function computeUnreadAlertState(
  currentKeys: string[],
  storedSeen: string[],
  isOnAlertsPage: boolean,
): { unreadCount: number; nextSeenKeys: string[] } {
  if (isOnAlertsPage) {
    return {
      unreadCount: 0,
      nextSeenKeys: [...currentKeys],
    };
  }

  const activeSet = new Set(currentKeys);
  const validSeen = storedSeen.filter((k) => activeSet.has(k));
  const seenSet = new Set(validSeen);
  const unreadCount = currentKeys.filter((k) => !seenSet.has(k)).length;

  return {
    unreadCount,
    nextSeenKeys: validSeen,
  };
}

export function RootLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout, updateUser } = useAuth();

  // --- Unread Alerts Notification Badge State ---
  const [unreadAlertCount, setUnreadAlertCount] = useState<number>(0);
  const [activeAlertKeys, setActiveAlertKeys] = useState<string[]>([]);

  // --- Profile Modal States ---
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);
  const [profileForm, setProfileForm] = useState({
    full_name: "",
    current_password: "",
    new_password: "",
    confirm_password: "",
  });
  const [isSaving, setIsSaving] = useState(false);
  const [profileError, setProfileError] = useState("");
  const [passwordError, setPasswordError] = useState("");
  const [profileSuccess, setProfileSuccess] = useState("");
  const { showWarning, secondsRemaining, extendSession, handleExpire } =
    useSessionTimeout();
  const API_BASE_URL = import.meta.env.VITE_API_URL ?? "";
  const CONFIG_API_BASE = import.meta.env.VITE_API_BASE_URL ?? "";

  useEffect(() => {
    if (!user) {
      navigate("/login");
    }
  }, [user, navigate]);

  const seenStorageKey = user ? `seen_alerts_user_${user.id}` : "";

  useEffect(() => {
    if (!user || user.mustResetPassword || !seenStorageKey) return;

    let isCancelled = false;

    const pollAlertNotifications = async () => {
      try {
        const [groupsRes, labsRes] = await Promise.all([
          fetch(`${CONFIG_API_BASE}/api/config/labgroups`, {
            credentials: "include",
          }),
          fetch(`${CONFIG_API_BASE}/api/config/labs`, {
            credentials: "include",
          }),
        ]);
        if (!groupsRes.ok || !labsRes.ok || isCancelled) return;

        const labGroups: unknown = await groupsRes.json();
        const labs: unknown = await labsRes.json();
        if (!Array.isArray(labGroups) || !Array.isArray(labs) || isCancelled) {
          return;
        }

        const currentKeys = buildAlertNotificationKeys(
          labGroups as AlertLabGroupSummary[],
          labs as AlertLabSummary[],
          user,
        );

        let storedSeen: string[] = [];
        try {
          const raw = localStorage.getItem(seenStorageKey);
          if (raw) {
            const parsed: unknown = JSON.parse(raw);
            if (Array.isArray(parsed)) {
              storedSeen = parsed.filter(
                (item): item is string => typeof item === "string",
              );
            }
          }
        } catch {
          storedSeen = [];
        }

        const isOnAlertsPage = location.pathname.startsWith("/alerts");
        const { unreadCount, nextSeenKeys } = computeUnreadAlertState(
          currentKeys,
          storedSeen,
          isOnAlertsPage,
        );

        localStorage.setItem(seenStorageKey, JSON.stringify(nextSeenKeys));
        setActiveAlertKeys(currentKeys);
        setUnreadAlertCount(unreadCount);
      } catch (err) {
        console.error("Failed to check alert notifications:", err);
      }
    };

    void pollAlertNotifications();
    const intervalId = window.setInterval(() => {
      void pollAlertNotifications();
    }, 15000);

    return () => {
      isCancelled = true;
      window.clearInterval(intervalId);
    };
  }, [user, seenStorageKey, location.pathname, CONFIG_API_BASE]);

  // Clear badge immediately when navigating to /alerts
  const handleNavClick = (path: string) => {
    if (path === "/alerts" && seenStorageKey) {
      localStorage.setItem(seenStorageKey, JSON.stringify(activeAlertKeys));
      setUnreadAlertCount(0);
    }
  };

  if (!user) {
    return null;
  }

  // --- Handlers ---
  const openProfileModal = () => {
    setProfileForm({
      full_name: user.fullName || "",
      current_password: "",
      new_password: "",
      confirm_password: "",
    });
    setProfileError("");
    setPasswordError("");
    setProfileSuccess("");
    setIsProfileModalOpen(true);
  };

  const handleProfileSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setProfileError("");
    setProfileSuccess("");

    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/me`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({ full_name: profileForm.full_name }),
      });

      if (res.ok) {
        updateUser({ fullName: profileForm.full_name });
        setProfileSuccess("Profile updated successfully.");
      } else {
        const errorData = await res.json();
        setProfileError(errorData.detail || "Failed to update profile.");
      }
    } catch {
      setProfileError("A network error occurred. Please try again.");
    } finally {
      setIsSaving(false);
    }
  };

  const handlePasswordReset = async (e: React.FormEvent) => {
    e.preventDefault();
    setPasswordError("");

    // Frontend validation
    if (!profileForm.current_password)
      return setPasswordError("Current password is required.");
    if (profileForm.new_password.length < 8)
      return setPasswordError("New password must be at least 8 characters.");
    if (profileForm.new_password === profileForm.current_password)
      return setPasswordError(
        "New password must differ from your current password.",
      );
    if (profileForm.new_password !== profileForm.confirm_password)
      return setPasswordError("Passwords do not match.");

    setIsSaving(true);
    try {
      const res = await fetch(`${API_BASE_URL}/api/auth/reset-password`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify({
          current_password: profileForm.current_password,
          new_password: profileForm.new_password,
        }),
      });

      if (res.ok) {
        setProfileForm((prev) => ({
          ...prev,
          current_password: "",
          new_password: "",
          confirm_password: "",
        }));
        setProfileSuccess("Password reset successfully.");
      } else {
        const errorData = await res.json();
        if (res.status === 400) {
          setPasswordError("Current password is incorrect.");
        } else {
          setPasswordError(errorData.detail || "Failed to reset password.");
        }
      }
    } catch {
      setPasswordError("A network error occurred. Please try again.");
    } finally {
      setIsSaving(false);
    }
  };

  return (
    <div className="flex h-screen bg-[#f8f9fa]">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-border flex flex-col z-10">
        {/* Logo/Brand */}
        <div className="h-16 border-b border-border flex items-center px-6">
          <h1 className="text-xl font-semibold text-[#1e3a8a]">Lab Budget</h1>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-4">
          <ul className="space-y-1 px-3">
            {navigation
              .filter((item) => {
                if (!user) return false;
                if (user.mustResetPassword) return false;
                return item.roles.includes(user.role);
              })
              .map((item) => {
                const Icon = item.icon;
                const isActive =
                  item.path === "/"
                    ? location.pathname === "/"
                    : location.pathname.startsWith(item.path);
                return (
                  <li key={item.path}>
                    <Link
                      to={item.path}
                      onClick={() => handleNavClick(item.path)}
                      className={cn(
                        "flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors",
                        isActive
                          ? "bg-[#1e3a8a] text-white"
                          : "text-[#475569] hover:bg-[#f1f5f9]",
                      )}
                    >
                      <Icon className="h-5 w-5 shrink-0" />
                      <span className="text-sm font-medium flex-1">
                        {item.name}
                      </span>
                      {item.path === "/alerts" && unreadAlertCount > 0 && (
                        <span
                          className={cn(
                            "ml-auto inline-flex items-center justify-center min-w-[20px] h-5 px-1.5 text-[11px] font-bold leading-none rounded-full shadow-xs",
                            isActive
                              ? "bg-white text-[#dc2626]"
                              : "bg-[#dc2626] text-white",
                          )}
                        >
                          {unreadAlertCount}
                        </span>
                      )}
                    </Link>
                  </li>
                );
              })}
          </ul>
        </nav>

        {/* User section */}
        <div className="border-t border-border p-4">
          {/* THE CLICKABLE USER CARD */}
          <div
            onClick={openProfileModal}
            className="flex items-center gap-3 mb-2 p-2 -mx-2 rounded-lg hover:bg-[#f1f5f9] cursor-pointer transition-colors group"
            title="Edit Profile"
          >
            <div className="h-9 w-9 rounded-full bg-[#1e3a8a] flex items-center justify-center text-white text-sm font-medium group-hover:bg-[#1e40af] transition-colors shrink-0">
              {(user?.fullName || "User")
                .split(" ")
                .map((n) => n[0])
                .join("")
                .toUpperCase()
                .slice(0, 2)}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground truncate group-hover:text-[#1e3a8a] transition-colors">
                {user?.fullName || "Loading..."}
              </p>
              <p className="text-xs text-muted-foreground truncate capitalize">
                {user?.role === "teamlead"
                  ? "Team Lead"
                  : user?.role === "labic"
                    ? "Lab IC"
                    : user?.role
                      ? "Admin"
                      : "Connecting..."}
              </p>
            </div>
          </div>

          <button
            onClick={() => {
              logout();
              navigate("/login");
            }}
            className="w-full flex items-center gap-2 px-3 py-2 text-sm text-[#dc2626] hover:bg-[#fef2f2] rounded-lg transition-colors"
          >
            <LogOut className="h-4 w-4" />
            <span>Sign Out</span>
          </button>
        </div>
      </aside>

      {/* Main content */}
      <div className="flex-1 flex flex-col overflow-hidden">
        {/* Header */}
        <header className="h-16 bg-white border-b border-border flex items-center justify-between px-6">
          <div className="flex items-center gap-4">
            <div>
              <h2 className="text-lg font-semibold text-foreground">
                {navigation.find((item) =>
                  item.path === "/"
                    ? location.pathname === "/"
                    : location.pathname.startsWith(item.path),
                )?.name || "Dashboard"}
              </h2>
            </div>
          </div>
          <div className="flex items-center gap-4">
            {FEATURES.headerNotifications && (
              <button className="relative p-2 hover:bg-muted rounded-lg transition-colors">
                <Bell className="h-5 w-5 text-muted-foreground" />
                <span className="absolute top-1.5 right-1.5 h-2 w-2 bg-[#dc2626] rounded-full"></span>
              </button>
            )}
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>

      {/* ===================== */}
      {/* EDIT PROFILE MODAL    */}
      {/* ===================== */}
      {isProfileModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 backdrop-blur-sm px-4">
          <div className="bg-white w-full max-w-md rounded-xl shadow-xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-gray-50/50">
              <h3 className="text-lg font-semibold text-gray-800">
                Edit Profile
              </h3>
              <button
                onClick={() => setIsProfileModalOpen(false)}
                className="text-gray-400 hover:text-gray-600 hover:bg-gray-100 p-1.5 rounded-md transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>

            <div className="p-6 space-y-6">
              {/* Success message */}
              {profileSuccess && (
                <div className="p-3 text-sm text-green-700 bg-green-50 border border-green-100 rounded-lg">
                  {profileSuccess}
                </div>
              )}

              {/* ── Section 1: Profile ── */}
              <form onSubmit={handleProfileSubmit} className="space-y-4">
                <h4 className="text-sm font-semibold text-gray-800">Profile</h4>

                {profileError && (
                  <div className="p-3 text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg">
                    {profileError}
                  </div>
                )}

                <div>
                  <label className="block text-sm font-medium text-gray-700 mb-1">
                    Full Name
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <UserIcon className="h-4 w-4 text-gray-400" />
                    </div>
                    <input
                      type="text"
                      required
                      className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#1e3a8a] focus:border-[#1e3a8a] outline-none transition-all"
                      value={profileForm.full_name}
                      onChange={(e) =>
                        setProfileForm({
                          ...profileForm,
                          full_name: e.target.value,
                        })
                      }
                    />
                  </div>
                </div>

                <div className="flex justify-end">
                  <button
                    type="submit"
                    disabled={isSaving}
                    className="px-4 py-2 text-sm font-medium text-white bg-[#1e3a8a] rounded-lg hover:bg-[#1e40af] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {isSaving ? "Saving..." : "Save Name"}
                  </button>
                </div>
              </form>

              {/* ── Section 2: Password ── */}
              <form
                onSubmit={handlePasswordReset}
                className="space-y-4 pt-4 border-t border-gray-100"
              >
                <h4 className="text-sm font-semibold text-gray-800">
                  Change Password{" "}
                  <span className="text-gray-400 font-normal">(Optional)</span>
                </h4>

                {passwordError && (
                  <div className="p-3 text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg">
                    {passwordError}
                  </div>
                )}

                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Current Password
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <Lock className="h-4 w-4 text-gray-400" />
                    </div>
                    <input
                      type="password"
                      autoComplete="current-password"
                      placeholder="Enter current password"
                      className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#1e3a8a] focus:border-[#1e3a8a] outline-none transition-all placeholder:text-sm"
                      value={profileForm.current_password}
                      onChange={(e) =>
                        setProfileForm({
                          ...profileForm,
                          current_password: e.target.value,
                        })
                      }
                    />
                  </div>
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    New Password
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <Lock className="h-4 w-4 text-gray-400" />
                    </div>
                    <input
                      type="password"
                      autoComplete="new-password"
                      placeholder="Min. 8 characters"
                      className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#1e3a8a] focus:border-[#1e3a8a] outline-none transition-all placeholder:text-sm"
                      value={profileForm.new_password}
                      onChange={(e) =>
                        setProfileForm({
                          ...profileForm,
                          new_password: e.target.value,
                        })
                      }
                    />
                  </div>
                  {profileForm.new_password.length > 0 &&
                    profileForm.new_password.length < 8 && (
                      <p className="text-xs text-amber-600 mt-1.5 font-medium">
                        Password must be at least 8 characters
                      </p>
                    )}
                </div>

                <div>
                  <label className="block text-xs font-medium text-gray-600 mb-1">
                    Confirm New Password
                  </label>
                  <div className="relative">
                    <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                      <Lock className="h-4 w-4 text-gray-400" />
                    </div>
                    <input
                      type="password"
                      autoComplete="new-password"
                      placeholder="Re-enter new password"
                      className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#1e3a8a] focus:border-[#1e3a8a] outline-none transition-all placeholder:text-sm"
                      value={profileForm.confirm_password}
                      onChange={(e) =>
                        setProfileForm({
                          ...profileForm,
                          confirm_password: e.target.value,
                        })
                      }
                    />
                  </div>
                  {profileForm.confirm_password.length > 0 &&
                    profileForm.new_password !==
                      profileForm.confirm_password && (
                      <p className="text-xs text-amber-600 mt-1.5 font-medium">
                        Passwords do not match
                      </p>
                    )}
                </div>

                <div className="flex justify-end gap-3 pt-2">
                  <button
                    type="button"
                    onClick={() => setIsProfileModalOpen(false)}
                    className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    disabled={
                      isSaving ||
                      !profileForm.current_password ||
                      profileForm.new_password.length < 8 ||
                      profileForm.new_password !== profileForm.confirm_password
                    }
                    className="px-4 py-2 text-sm font-medium text-white bg-[#1e3a8a] rounded-lg hover:bg-[#1e40af] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                  >
                    {isSaving ? "Saving..." : "Reset Password"}
                  </button>
                </div>
              </form>
            </div>
          </div>
        </div>
      )}
      {/* SESSION TIMEOUT WARNING MODAL */}
      {showWarning && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 backdrop-blur-sm px-4">
          <div className="bg-white w-full max-w-sm rounded-xl shadow-xl overflow-hidden">
            <div className="px-6 py-4 border-b border-gray-100 bg-amber-50">
              <div className="flex items-center gap-3">
                <div className="p-2 rounded-full bg-amber-100">
                  <Bell className="h-5 w-5 text-amber-600" />
                </div>
                <h3 className="text-lg font-semibold text-gray-800">
                  Session Expiring
                </h3>
              </div>
            </div>

            <div className="p-6 space-y-4">
              <p className="text-sm text-gray-600">
                Your session will expire in{" "}
                <span className="font-semibold text-amber-600">
                  {Math.floor(secondsRemaining / 60)}:
                  {String(secondsRemaining % 60).padStart(2, "0")}
                </span>
                . Would you like to stay logged in?
              </p>

              {/* Countdown bar */}
              <div className="w-full bg-gray-100 rounded-full h-1.5">
                <div
                  className="bg-amber-500 h-1.5 rounded-full transition-all duration-1000"
                  style={{
                    width: `${(secondsRemaining / (WARNING_BEFORE_EXPIRY_MS / 1000)) * 100}%`,
                  }}
                />
              </div>

              <div className="flex gap-3 pt-2">
                <button
                  onClick={handleExpire}
                  className="flex-1 px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  Sign Out
                </button>
                <button
                  onClick={extendSession}
                  className="flex-1 px-4 py-2 text-sm font-medium text-white bg-[#1e3a8a] rounded-lg hover:bg-[#1e40af] transition-colors"
                >
                  Stay Logged In
                </button>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* Floating AI assistant — fixed-position, so it sits outside the
          page flow and appears on every authenticated route. */}
      {FEATURES.askAi && <AskAiWidget />}
    </div>
  );
}