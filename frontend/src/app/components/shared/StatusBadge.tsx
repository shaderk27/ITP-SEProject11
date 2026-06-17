import { cn } from "../ui/utils";

interface StatusBadgeProps {
  status:
    | "healthy"
    | "warning"
    | "exceeded"
    | "info"
    | "general"
    | "pending"
    | "approved"
    | "rejected"
    | "new"
    | "override";
  children: React.ReactNode;
}

const statusStyles = {
  healthy: "bg-[#10b981]/10 text-[#059669] border-[#10b981]/20",
  warning: "bg-[#f59e0b]/10 text-[#d97706] border-[#f59e0b]/20",
  exceeded: "bg-[#ef4444]/10 text-[#dc2626] border-[#ef4444]/20",
  info: "bg-[#3b82f6]/10 text-[#2563eb] border-[#3b82f6]/20",
  general: "bg-[#6b7280]/10 text-[#4b5563] border-[#6b7280]/20",
  pending: "bg-[#f59e0b]/10 text-[#d97706] border-[#f59e0b]/20",
  approved: "bg-[#10b981]/10 text-[#059669] border-[#10b981]/20",
  rejected: "bg-[#ef4444]/10 text-[#dc2626] border-[#ef4444]/20",
  new: "bg-[#3b82f6]/10 text-[#2563eb] border-[#3b82f6]/20",
  override: "bg-[#8b5cf6]/10 text-[#7c3aed] border-[#8b5cf6]/20",
};

export function StatusBadge({ status, children }: StatusBadgeProps) {
  return (
    <span
      className={cn(
        "inline-flex items-center px-2.5 py-0.5 rounded-md text-xs font-medium border",
        statusStyles[status]
      )}
    >
      {children}
    </span>
  );
}
