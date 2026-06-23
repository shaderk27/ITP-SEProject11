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
  Lock
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
  { name: "Create User", path: "/users/create", icon: UserPlus, roles: ["admin"] },
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
  const { user, logout, updateUser } = useAuth(); // Make sure updateUser is exported from AuthContext!

  // --- Profile Modal States ---
  const [isProfileModalOpen, setIsProfileModalOpen] = useState(false);
  const [profileForm, setProfileForm] = useState({ full_name: "", current_password: "", new_password: "" });
  const [isSaving, setIsSaving] = useState(false);
  const [profileError, setProfileError] = useState("");
  
  const API_BASE_URL = import.meta.env.VITE_API_URL ?? "http://localhost:8080";

  useEffect(() => {
    if (!user) {
      navigate("/login");
    }
  }, [user, navigate]);

  if (!user) {
    return null;
  }

  // --- Handlers ---
  const openProfileModal = () => {
    setProfileForm({ full_name: user.fullName || "", current_password: "", new_password: "" });
    setProfileError("");
    setIsProfileModalOpen(true);
  };

  const handleProfileSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setIsSaving(true);
    setProfileError("");

    try {
      // Only attach password fields to the payload if the user typed a new password
      const payload = {
        full_name: profileForm.full_name,
        ...(profileForm.new_password ? { 
          current_password: profileForm.current_password,
          new_password: profileForm.new_password 
        } : {})
      };

      const res = await fetch(`${API_BASE_URL}/api/auth/me`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        credentials: "include",
        body: JSON.stringify(payload)
      });

      if (res.ok) {
        // Instantly update the bottom-left corner UI without refreshing!
        updateUser({ fullName: profileForm.full_name });
        setIsProfileModalOpen(false);
      } else {
        const errorData = await res.json();
        setProfileError(errorData.detail || "Failed to update profile");
      }
    } catch (err) {
      setProfileError("A network error occurred. Please try again.");
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

      {/* ===================== */}
      {/* EDIT PROFILE MODAL    */}
      {/* ===================== */}
      {isProfileModalOpen && (
        <div className="fixed inset-0 bg-black/50 flex items-center justify-center z-50 backdrop-blur-sm px-4">
          <div className="bg-white w-full max-w-md rounded-xl shadow-xl overflow-hidden animate-in fade-in zoom-in-95 duration-200">
            <div className="px-6 py-4 border-b border-gray-100 flex justify-between items-center bg-gray-50/50">
              <h3 className="text-lg font-semibold text-gray-800">Edit Profile</h3>
              <button 
                onClick={() => setIsProfileModalOpen(false)} 
                className="text-gray-400 hover:text-gray-600 hover:bg-gray-100 p-1.5 rounded-md transition-colors"
              >
                <X className="h-5 w-5" />
              </button>
            </div>
            
            <form onSubmit={handleProfileSubmit} className="p-6 space-y-5">
              
              {/* Error Message Display */}
              {profileError && (
                <div className="p-3 text-sm text-red-600 bg-red-50 border border-red-100 rounded-lg">
                  {profileError}
                </div>
              )}

              <div>
                <label className="block text-sm font-medium text-gray-700 mb-1">Full Name</label>
                <div className="relative">
                  <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                    <UserIcon className="h-4 w-4 text-gray-400" />
                  </div>
                  <input 
                    type="text" 
                    required 
                    className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#1e3a8a] focus:border-[#1e3a8a] outline-none transition-all" 
                    value={profileForm.full_name} 
                    onChange={(e) => setProfileForm({...profileForm, full_name: e.target.value})} 
                  />
                </div>
              </div>

              <div className="pt-4 border-t border-gray-100">
                <h4 className="text-sm font-semibold text-gray-800 mb-3">Change Password <span className="text-gray-400 font-normal">(Optional)</span></h4>
                
                <div className="space-y-4">
                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">Current Password</label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <Lock className="h-4 w-4 text-gray-400" />
                      </div>
                      <input 
                        type="password" 
                        placeholder="Required if setting a new password"
                        className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#1e3a8a] focus:border-[#1e3a8a] outline-none transition-all placeholder:text-sm" 
                        value={profileForm.current_password} 
                        onChange={(e) => setProfileForm({...profileForm, current_password: e.target.value})} 
                      />
                    </div>
                  </div>

                  <div>
                    <label className="block text-xs font-medium text-gray-600 mb-1">New Password</label>
                    <div className="relative">
                      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none">
                        <Lock className="h-4 w-4 text-gray-400" />
                      </div>
                      <input 
                        type="password" 
                        placeholder="Must be at least 8 characters"
                        className="w-full pl-10 pr-3 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-[#1e3a8a] focus:border-[#1e3a8a] outline-none transition-all placeholder:text-sm" 
                        value={profileForm.new_password} 
                        onChange={(e) => setProfileForm({...profileForm, new_password: e.target.value})} 
                      />
                    </div>
                    {/* Real-time frontend validation warning */}
                    {profileForm.new_password.length > 0 && profileForm.new_password.length < 8 && (
                      <p className="text-xs text-amber-600 mt-1.5 font-medium">Password must be at least 8 characters</p>
                    )}
                  </div>
                </div>
              </div>

              <div className="flex justify-end gap-3 pt-4 border-t border-gray-100">
                <button 
                  type="button" 
                  onClick={() => setIsProfileModalOpen(false)}
                  className="px-4 py-2 text-sm font-medium text-gray-700 bg-white border border-gray-300 rounded-lg hover:bg-gray-50 transition-colors"
                >
                  Cancel
                </button>
                <button 
                  type="submit" 
                  disabled={isSaving || (profileForm.new_password.length > 0 && (profileForm.new_password.length < 8 || !profileForm.current_password))}
                  className="px-4 py-2 text-sm font-medium text-white bg-[#1e3a8a] rounded-lg hover:bg-[#1e40af] disabled:opacity-50 disabled:cursor-not-allowed transition-colors"
                >
                  {isSaving ? "Saving..." : "Save Changes"}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}