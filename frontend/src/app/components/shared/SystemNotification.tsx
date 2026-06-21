import { CheckCircle, Info, AlertTriangle } from "lucide-react";
import { Card } from "../ui/card";

interface SystemNotificationProps {
  type: "success" | "info" | "warning";
  title: string;
  message: string;
}

export function SystemNotification({ type, title, message }: SystemNotificationProps) {
  const config = {
    success: {
      bg: "bg-[#f0fdf4]",
      border: "border-[#bbf7d0]",
      icon: CheckCircle,
      iconColor: "text-[#059669]",
      titleColor: "text-[#047857]",
      textColor: "text-[#065f46]",
    },
    info: {
      bg: "bg-[#f0f9ff]",
      border: "border-[#bfdbfe]",
      icon: Info,
      iconColor: "text-[#2563eb]",
      titleColor: "text-[#1e40af]",
      textColor: "text-[#1e3a8a]",
    },
    warning: {
      bg: "bg-[#fef3c7]",
      border: "border-[#fde68a]",
      icon: AlertTriangle,
      iconColor: "text-[#d97706]",
      titleColor: "text-[#92400e]",
      textColor: "text-[#92400e]",
    },
  };

  const style = config[type];
  const Icon = style.icon;

  return (
    <Card className={`p-4 ${style.bg} ${style.border}`}>
      <div className="flex items-start gap-3">
        <Icon className={`h-5 w-5 ${style.iconColor} flex-shrink-0 mt-0.5`} />
        <div>
          <h4 className={`text-sm font-semibold ${style.titleColor} mb-1`}>
            {title}
          </h4>
          <p className={`text-sm ${style.textColor}`}>{message}</p>
        </div>
      </div>
    </Card>
  );
}
