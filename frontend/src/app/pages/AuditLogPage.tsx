import { Card } from "../components/ui/card";
import { FilterBar } from "../components/shared/FilterBar";
import { StatusBadge } from "../components/shared/StatusBadge";

const mockAuditLog = [
  {
    timestamp: "2026-05-23 14:32:15",
    user: "John Doe (Admin)",
    action: "Approved Record",
    entity: "PR-2026-1527",
    details: "Lab: W4L1, Category: Equipment",
    oldValue: "Lab: General",
    newValue: "Lab: W4L1",
  },
  {
    timestamp: "2026-05-23 14:28:42",
    user: "Sarah Chen (Team Lead)",
    action: "Rejected Record",
    entity: "PR-2026-1529",
    details: "Insufficient information",
    oldValue: "-",
    newValue: "-",
  },
  {
    timestamp: "2026-05-23 14:15:03",
    user: "System",
    action: "Upload Processed",
    entity: "UP-2024-153",
    details: "152 records processed, 28 pending review",
    oldValue: "-",
    newValue: "-",
  },
  {
    timestamp: "2026-05-23 14:10:28",
    user: "Sarah Chen (Team Lead)",
    action: "File Uploaded",
    entity: "UP-2024-153",
    details: "PR_Data_May2026.xlsx",
    oldValue: "-",
    newValue: "-",
  },
  {
    timestamp: "2026-05-23 11:45:19",
    user: "John Doe (Admin)",
    action: "Budget Updated",
    entity: "W3L1",
    details: "Annual budget adjustment",
    oldValue: "$60,000",
    newValue: "$65,000",
  },
  {
    timestamp: "2026-05-23 10:22:37",
    user: "Sarah Chen (Team Lead)",
    action: "Override Classification",
    entity: "PR-2026-1401",
    details: "Manual lab assignment",
    oldValue: "Lab: General",
    newValue: "Lab: W3L1",
  },
  {
    timestamp: "2026-05-22 16:55:11",
    user: "System",
    action: "Alert Triggered",
    entity: "W3L1",
    details: "Critical threshold exceeded at 112% (95%+ alert)",
    oldValue: "-",
    newValue: "-",
  },
  {
    timestamp: "2026-05-22 15:30:45",
    user: "John Doe (Admin)",
    action: "Lab Alias Added",
    entity: "W3L1",
    details: "Added alias: Food PP for lab mapping",
    oldValue: "-",
    newValue: "Food PP",
  },
  {
    timestamp: "2026-05-22 14:18:20",
    user: "John Doe (Admin)",
    action: "Threshold Updated",
    entity: "System Config",
    details: "Updated alert thresholds to 50%, 80%, 95%",
    oldValue: "50%, 85%, 100%",
    newValue: "50%, 80%, 95%",
  },
  {
    timestamp: "2026-05-22 13:05:52",
    user: "Sarah Chen (Team Lead)",
    action: "Approved Record",
    entity: "PR-2026-1520",
    details: "Lab: W3L2, Category: Supplies",
    oldValue: "Lab: General",
    newValue: "Lab: W3L2",
  },
  {
    timestamp: "2026-05-22 10:15:33",
    user: "Alice Johnson (Lab IC)",
    action: "Viewed Dashboard",
    entity: "W3L1",
    details: "Accessed lab-specific dashboard data",
    oldValue: "-",
    newValue: "-",
  },
  {
    timestamp: "2026-05-22 09:42:18",
    user: "Alice Johnson (Lab IC)",
    action: "AI Query",
    entity: "Chatbot",
    details: "Asked: 'What is my lab utilization?'",
    oldValue: "-",
    newValue: "-",
  },
];

const actionColors: Record<string, any> = {
  "Approved Record": "approved",
  "Rejected Record": "rejected",
  "Upload Processed": "info",
  "File Uploaded": "info",
  "Budget Updated": "warning",
  "Override Classification": "override",
  "Alert Triggered": "warning",
  "Lab Alias Added": "new",
  "Threshold Updated": "warning",
};

export function AuditLogPage() {
  return (
    <div className="h-full overflow-auto bg-[#f8f9fa]">
      <FilterBar
        searchPlaceholder="Search audit log by user, action, or entity..."
        filters={[
          {
            label: "Date Range",
            options: [
              { value: "today", label: "Today" },
            ],
          },
          {
            label: "Action Type",
            options: [
              { value: "all", label: "All Actions" },
              { value: "upload", label: "Uploads" },
              { value: "review", label: "Reviews" },
              { value: "config", label: "Configuration" },
              { value: "system", label: "System" },
            ],
          },
          {
            label: "User",
            options: [
              { value: "all", label: "All Users" },
              { value: "johndoe", label: "John Doe" },
              { value: "sarahchen", label: "Sarah Chen" },
              { value: "system", label: "System" },
            ],
          },
        ]}
        showExport={true}
      />

      <div className="p-6">
        <div className="mb-6">
          <h2 className="text-2xl font-semibold text-foreground">Audit Log</h2>
          <p className="text-sm text-muted-foreground mt-1">
            Complete history of system activities and changes
          </p>
        </div>

        <Card className="bg-white border-border overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-[#f8f9fa]">
                <tr className="border-b border-border">
                  <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                    Timestamp
                  </th>
                  <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                    User
                  </th>
                  <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                    Action
                  </th>
                  <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                    Entity
                  </th>
                  <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                    Details
                  </th>
                  <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                    Old Value
                  </th>
                  <th className="text-left p-4 text-sm font-medium text-muted-foreground">
                    New Value
                  </th>
                </tr>
              </thead>
              <tbody>
                {mockAuditLog.map((log, idx) => (
                  <tr
                    key={idx}
                    className="border-b border-border last:border-0 hover:bg-[#f8f9fa] transition-colors"
                  >
                    <td className="p-4">
                      <p className="text-sm text-muted-foreground whitespace-nowrap">
                        {log.timestamp}
                      </p>
                    </td>
                    <td className="p-4">
                      <p className="text-sm font-medium text-foreground">
                        {log.user}
                      </p>
                    </td>
                    <td className="p-4">
                      <StatusBadge status={actionColors[log.action] || "info"}>
                        {log.action}
                      </StatusBadge>
                    </td>
                    <td className="p-4">
                      <p className="text-sm font-medium text-[#1e3a8a]">
                        {log.entity}
                      </p>
                    </td>
                    <td className="p-4">
                      <p className="text-sm text-muted-foreground max-w-xs">
                        {log.details}
                      </p>
                    </td>
                    <td className="p-4">
                      <p className="text-sm text-muted-foreground">
                        {log.oldValue}
                      </p>
                    </td>
                    <td className="p-4">
                      <p className="text-sm text-muted-foreground">
                        {log.newValue}
                      </p>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Pagination */}
          <div className="border-t border-border p-4 flex items-center justify-between">
            <p className="text-sm text-muted-foreground">
              Showing 1 to 10 of 2,847 entries
            </p>
            <div className="flex gap-2">
              <button className="px-3 py-1 text-sm border border-border rounded hover:bg-[#f8f9fa] disabled:opacity-50 disabled:cursor-not-allowed">
                Previous
              </button>
              <button className="px-3 py-1 text-sm border border-border rounded bg-[#1e3a8a] text-white">
                1
              </button>
              <button className="px-3 py-1 text-sm border border-border rounded hover:bg-[#f8f9fa]">
                2
              </button>
              <button className="px-3 py-1 text-sm border border-border rounded hover:bg-[#f8f9fa]">
                3
              </button>
              <button className="px-3 py-1 text-sm border border-border rounded hover:bg-[#f8f9fa]">
                Next
              </button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}
