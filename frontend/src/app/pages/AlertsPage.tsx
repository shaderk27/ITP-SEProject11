import { Card } from "../components/ui/card";
import { FilterBar } from "../components/shared/FilterBar";
import { StatusBadge } from "../components/shared/StatusBadge";
import { AlertCircle, TrendingUp, Mail, Info } from "lucide-react";
import { Button } from "../components/ui/button";
import { useAuth } from "../context/AuthContext";

const mockAlerts = [
  {
    id: "ALT-001",
    type: "exceeded",
    lab: "W3L1 - Food Pilot Plant",
    message: "Critical threshold exceeded (95%+)",
    budget: 65000,
    actual: 72800,
    utilization: 112.0,
    threshold: 95,
    triggeredDate: "2026-05-20",
    emailSent: true,
  },
  {
    id: "ALT-002",
    type: "warning",
    lab: "W4L2 - Materials Analysis",
    message: "Alert threshold reached (80%)",
    budget: 50000,
    actual: 44000,
    utilization: 88.0,
    threshold: 80,
    triggeredDate: "2026-05-19",
    emailSent: true,
  },
  {
    id: "ALT-003",
    type: "warning",
    lab: "W3 - Food Processing (Lab Group)",
    message: "Alert threshold reached (80%)",
    budget: 180000,
    actual: 158400,
    utilization: 88.0,
    threshold: 80,
    triggeredDate: "2026-05-18",
    emailSent: true,
  },
  {
    id: "ALT-004",
    type: "info",
    lab: "W4L1 - Tensile Testing",
    message: "Warning threshold reached (50%)",
    budget: 55000,
    actual: 38100,
    utilization: 69.3,
    threshold: 50,
    triggeredDate: "2026-05-17",
    emailSent: false,
  },
];

export function AlertsPage() {
  const { user } = useAuth();

  // Filter alerts based on user's assigned labs
  const filteredAlerts = mockAlerts.filter((alert) => {
    if (user?.role === "admin") return true;
    if (user?.role === "teamlead") {
      return user.assignedLabs?.some((lab) => alert.lab.includes(lab));
    }
    return false;
  });

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa]">
      <FilterBar
        searchPlaceholder="Search alerts..."
        filters={[
          {
            label: "Alert Type",
            options: [
              { value: "all", label: "All Types" },
              { value: "exceeded", label: "Budget Exceeded" },
              { value: "warning", label: "Warning" },
              { value: "info", label: "Info" },
            ],
          },
          {
            label: "Lab Group",
            options: [
              { value: "all", label: "All Lab Groups" },
              { value: "w3", label: "W3 - Food Processing" },
              { value: "w4", label: "W4 - Materials Testing" },
            ],
          },
          {
            label: "Status",
            options: [
              { value: "active", label: "Active" },
              { value: "resolved", label: "Resolved" },
            ],
          },
        ]}
      />

      <div className="p-6 space-y-6">
        <div>
          <h2 className="text-2xl font-semibold text-foreground">Alerts Center</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Budget threshold alerts and notifications
          </p>
        </div>

        {user?.role === "teamlead" && (
          <Card className="p-4 bg-[#f0f9ff] border-[#bfdbfe]">
            <div className="flex items-start gap-3">
              <Info className="h-5 w-5 text-[#2563eb] flex-shrink-0 mt-0.5" />
              <div>
                <p className="text-sm text-[#1e40af] font-medium">Team Lead View</p>
                <p className="text-xs text-[#1e3a8a] mt-1">
                  Showing alerts only for your assigned labs: {user.assignedLabs?.join(", ")}
                </p>
              </div>
            </div>
          </Card>
        )}

        <Card className="p-4 bg-[#fef3c7] border-[#fde68a]">
          <h4 className="text-sm font-semibold text-[#92400e] mb-2">
            Alert Threshold Levels
          </h4>
          <div className="grid grid-cols-3 gap-4 text-xs text-[#92400e]">
            <div>
              <div className="font-medium mb-1">⚠️ Warning (50%)</div>
              <div>Yellow alert sent to Team Lead</div>
            </div>
            <div>
              <div className="font-medium mb-1">🔶 Alert (80%)</div>
              <div>Orange alert to assigned Team Lead</div>
            </div>
            <div>
              <div className="font-medium mb-1">🚨 Critical (95%)</div>
              <div>Red alert - potential over-expenditure</div>
            </div>
          </div>
        </Card>

        {/* Alert Summary Cards */}
        <div className="grid grid-cols-1 md:grid-cols-3 gap-6">
          <Card className="p-6 bg-white border-border">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-lg bg-[#ef4444]/10 flex items-center justify-center">
                <AlertCircle className="h-6 w-6 text-[#dc2626]" />
              </div>
              <div>
                <p className="text-2xl font-semibold text-foreground">
                  {filteredAlerts.filter(a => a.type === "exceeded").length}
                </p>
                <p className="text-sm text-muted-foreground">Budget Exceeded</p>
              </div>
            </div>
          </Card>

          <Card className="p-6 bg-white border-border">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-lg bg-[#f59e0b]/10 flex items-center justify-center">
                <TrendingUp className="h-6 w-6 text-[#d97706]" />
              </div>
              <div>
                <p className="text-2xl font-semibold text-foreground">
                  {filteredAlerts.filter(a => a.type === "warning").length}
                </p>
                <p className="text-sm text-muted-foreground">Warnings</p>
              </div>
            </div>
          </Card>

          <Card className="p-6 bg-white border-border">
            <div className="flex items-center gap-4">
              <div className="h-12 w-12 rounded-lg bg-[#3b82f6]/10 flex items-center justify-center">
                <Mail className="h-6 w-6 text-[#2563eb]" />
              </div>
              <div>
                <p className="text-2xl font-semibold text-foreground">
                  {filteredAlerts.filter(a => a.emailSent).length}
                </p>
                <p className="text-sm text-muted-foreground">Emails Sent</p>
              </div>
            </div>
          </Card>
        </div>

        {/* Active Alerts */}
        <Card className="bg-white border-border">
          <div className="p-6 border-b border-border">
            <h3 className="text-lg font-semibold text-foreground">Active Alerts</h3>
          </div>
          <div className="divide-y divide-border">
            {filteredAlerts.map((alert) => {
              const alertConfig =
                alert.type === "exceeded"
                  ? {
                      bgColor: "bg-[#fef2f2]",
                      borderColor: "border-[#fecaca]",
                      iconColor: "text-[#dc2626]",
                    }
                  : alert.type === "warning"
                  ? {
                      bgColor: "bg-[#fef3c7]",
                      borderColor: "border-[#fde68a]",
                      iconColor: "text-[#d97706]",
                    }
                  : {
                      bgColor: "bg-[#f0f9ff]",
                      borderColor: "border-[#bfdbfe]",
                      iconColor: "text-[#2563eb]",
                    };

              return (
                <div key={alert.id} className="p-6">
                  <div
                    className={`${alertConfig.bgColor} ${alertConfig.borderColor} border rounded-lg p-4`}
                  >
                    <div className="flex items-start gap-4">
                      <AlertCircle
                        className={`h-6 w-6 ${alertConfig.iconColor} flex-shrink-0 mt-1`}
                      />
                      <div className="flex-1">
                        <div className="flex items-start justify-between mb-3">
                          <div>
                            <h4 className="font-semibold text-foreground mb-1">
                              {alert.lab}
                            </h4>
                            <p className="text-sm text-muted-foreground">
                              {alert.message}
                            </p>
                          </div>
                          <StatusBadge status={alert.type as any}>
                            {alert.type === "exceeded"
                              ? "Exceeded"
                              : alert.type === "warning"
                              ? "Warning"
                              : "Info"}
                          </StatusBadge>
                        </div>

                        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-4">
                          <div>
                            <p className="text-xs text-muted-foreground mb-1">
                              Budget
                            </p>
                            <p className="text-sm font-medium text-foreground">
                              ${alert.budget.toLocaleString()}
                            </p>
                          </div>
                          <div>
                            <p className="text-xs text-muted-foreground mb-1">
                              Actual Spend
                            </p>
                            <p className="text-sm font-medium text-foreground">
                              ${alert.actual.toLocaleString()}
                            </p>
                          </div>
                          <div>
                            <p className="text-xs text-muted-foreground mb-1">
                              Utilization
                            </p>
                            <p
                              className={`text-sm font-medium ${
                                alert.utilization > 100
                                  ? "text-[#dc2626]"
                                  : alert.utilization > 85
                                  ? "text-[#d97706]"
                                  : "text-[#059669]"
                              }`}
                            >
                              {alert.utilization}%
                            </p>
                          </div>
                          <div>
                            <p className="text-xs text-muted-foreground mb-1">
                              Threshold
                            </p>
                            <p className="text-sm font-medium text-foreground">
                              {alert.threshold}%
                            </p>
                          </div>
                        </div>

                        {/* Progress bar */}
                        <div className="mb-4">
                          <div className="w-full h-2 bg-white rounded-full overflow-hidden">
                            <div
                              className={`h-full ${
                                alert.utilization > 100
                                  ? "bg-[#dc2626]"
                                  : alert.utilization > 85
                                  ? "bg-[#d97706]"
                                  : "bg-[#059669]"
                              }`}
                              style={{
                                width: `${Math.min(alert.utilization, 100)}%`,
                              }}
                            />
                          </div>
                        </div>

                        <div className="flex items-center justify-between">
                          <div className="flex items-center gap-4 text-xs text-muted-foreground">
                            <span>Triggered: {alert.triggeredDate}</span>
                            <span className="flex items-center gap-1">
                              <Mail className="h-3 w-3" />
                              {alert.emailSent
                                ? `Email sent to ${user?.role === "admin" ? "Admin & Team Lead" : "Team Lead"}`
                                : "No email sent"}
                            </span>
                          </div>
                          <Button variant="outline" size="sm">
                            View Details
                          </Button>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              );
            })}
          </div>
        </Card>
      </div>
    </div>
  );
}
