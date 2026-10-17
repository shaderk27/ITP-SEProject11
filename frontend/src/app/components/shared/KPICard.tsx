import { Card } from "../ui/card";
import type { LucideIcon } from "lucide-react";
import { cn } from "../ui/utils";

interface KPICardProps {
  title: string;
  value: string | number;
  icon: LucideIcon;
  trend?: {
    value: string;
    isPositive: boolean;
  };
  status?: "success" | "warning" | "error" | "info";
}

const statusColors = {
  success: "bg-[#10b981]/10 text-[#059669]",
  warning: "bg-[#f59e0b]/10 text-[#d97706]",
  error: "bg-[#ef4444]/10 text-[#dc2626]",
  info: "bg-[#3b82f6]/10 text-[#2563eb]",
};

export function KPICard({ title, value, icon: Icon, trend, status }: KPICardProps) {
  return (
    <Card className="p-6 bg-white border-border">
      <div className="flex items-start justify-between">
        <div className="flex-1">
          <p className="text-sm text-muted-foreground mb-2">{title}</p>
          <p className="text-3xl font-semibold text-foreground">{value}</p>
          {trend && (
            <p
              className={cn(
                "text-sm mt-2",
                trend.isPositive ? "text-[#059669]" : "text-[#dc2626]"
              )}
            >
              {trend.value}
            </p>
          )}
        </div>
        <div
          className={cn(
            "h-12 w-12 rounded-lg flex items-center justify-center",
            status ? statusColors[status] : "bg-[#1e3a8a]/10 text-[#1e3a8a]"
          )}
        >
          <Icon className="h-6 w-6" />
        </div>
      </div>
    </Card>
  );
}
