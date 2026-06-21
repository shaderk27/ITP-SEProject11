import { useEffect } from "react";
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
} from "lucide-react";
import { cn } from "../ui/utils";
import { useAuth } from "../../context/AuthContext";
import type { UserRole } from "../../context/AuthContext";

interface NavItem {
  name: string;
  path: string;
  icon: any;
  roles: UserRole[];
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
  {
    name: "Reports",
    path: "/reports",
    icon: BarChart3,
    roles: ["admin", "teamlead", "labic"],
  },
  { name: "Alerts", path: "/alerts", icon: Bell, roles: ["admin", "teamlead"] },
  { name: "Audit Log", path: "/audit", icon: FileSearch, roles: ["admin"] },
  {
    name: "AI Chatbot",
    path: "/chatbot",
    icon: MessageSquare,
    roles: ["admin", "teamlead", "labic"],
  },
  { name: "System Config", path: "/config", icon: Settings, roles: ["admin"] },
];

export function RootLayout() {
  const location = useLocation();
  const navigate = useNavigate();
  const { user, logout } = useAuth();

  useEffect(() => {
    if (!user) {
      navigate("/login");
    }
  }, [user, navigate]);

  if (!user) {
    return null;
  }

  return (
    <div className="flex h-screen bg-[#f8f9fa]">
      {/* Sidebar */}
      <aside className="w-64 bg-white border-r border-border flex flex-col">
        {/* Logo/Brand */}
        <div className="h-16 border-b border-border flex items-center px-6">
          <h1 className="text-xl font-semibold text-[#1e3a8a]">Lab Budget</h1>
        </div>

        {/* Navigation */}
        <nav className="flex-1 overflow-y-auto py-4">
          <ul className="space-y-1 px-3">
            {navigation
              .filter((item) => user && item.roles.includes(user.role))
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
                      className={cn(
                        "flex items-center gap-3 px-3 py-2.5 rounded-lg transition-colors",
                        isActive
                          ? "bg-[#1e3a8a] text-white"
                          : "text-[#475569] hover:bg-[#f1f5f9]",
                      )}
                    >
                      <Icon className="h-5 w-5" />
                      <span className="text-sm font-medium">{item.name}</span>
                    </Link>
                  </li>
                );
              })}
          </ul>
        </nav>

        {/* User section */}
        <div className="border-t border-border p-4">
          <div className="flex items-center gap-3 mb-3">
            <div className="h-9 w-9 rounded-full bg-[#1e3a8a] flex items-center justify-center text-white text-sm font-medium">
              {/* Fallback to 'U' if fullName is missing, safely mapping initials */}
              {(user?.fullName || "User")
                .split(" ")
                .map((n) => n[0])
                .join("")
                .toUpperCase()}
            </div>
            <div className="flex-1 min-w-0">
              <p className="text-sm font-medium text-foreground truncate">
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
              {user?.assignedLabs && (
                <p className="text-xs text-muted-foreground">
                  {/* Assigned Labs: {user.assignedLabs.join(", ")} */}
                </p>
              )}
            </div>
          </div>
          <div className="flex items-center gap-4">
            <button className="relative p-2 hover:bg-muted rounded-lg transition-colors">
              <Bell className="h-5 w-5 text-muted-foreground" />
              <span className="absolute top-1.5 right-1.5 h-2 w-2 bg-[#dc2626] rounded-full"></span>
            </button>
          </div>
        </header>

        {/* Page content */}
        <main className="flex-1 overflow-auto">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
