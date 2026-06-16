import { Card } from "../ui/card";
import { Shield, Users, User } from "lucide-react";
import { useAuth } from "../../context/AuthContext";

export function RoleInfo() {
  const { user } = useAuth();

  if (!user) return null;

  const roleConfig = {
    admin: {
      icon: Shield,
      title: "Administrator",
      color: "bg-[#8b5cf6]/10 text-[#7c3aed] border-[#8b5cf6]/20",
      iconColor: "text-[#7c3aed]",
      permissions: [
        "Full system access",
        "Configure lab hierarchy and budgets",
        "View all labs and data",
        "Access audit logs",
        "Manage users and roles",
      ],
    },
    teamlead: {
      icon: Users,
      title: "Team Lead",
      color: "bg-[#059669]/10 text-[#047857] border-[#059669]/20",
      iconColor: "text-[#047857]",
      permissions: [
        "Upload PR data",
        "Resolve own upload batches",
        "View assigned lab group scope",
        "Receive budget alerts",
        "Edit assigned lab budgets",
      ],
    },
    labic: {
      icon: User,
      title: "Lab IC",
      color: "bg-[#2563eb]/10 text-[#1e40af] border-[#2563eb]/20",
      iconColor: "text-[#1e40af]",
      permissions: [
        "View own lab data only",
        "Access scoped reports and charts",
        "View PR records",
        "Read-only access",
      ],
    },
  };

  const config = roleConfig[user.role];
  const Icon = config.icon;

  return (
    <Card className={`p-4 border ${config.color}`}>
      <div className="flex items-start gap-3">
        <Icon className={`h-5 w-5 ${config.iconColor} flex-shrink-0 mt-0.5`} />
        <div className="flex-1">
          <h4 className="font-semibold text-sm mb-1">{config.title}</h4>
          <p className="text-xs opacity-90 mb-2">Logged in as {user.name}</p>
          {user.assignedLabs && (
            <p className="text-xs opacity-75 mb-2">
              Assigned: {user.assignedLabs.join(", ")}
            </p>
          )}
          <div className="text-xs opacity-75 space-y-0.5">
            {config.permissions.map((perm, idx) => (
              <div key={idx}>- {perm}</div>
            ))}
          </div>
        </div>
      </div>
    </Card>
  );
}
