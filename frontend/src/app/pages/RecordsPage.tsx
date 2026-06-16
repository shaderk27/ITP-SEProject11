import { Fragment, useState } from "react";
import { ChevronDown, ChevronRight, FileDown } from "lucide-react";
import { Card } from "../components/ui/card";
import { FilterBar } from "../components/shared/FilterBar";
import { StatusBadge } from "../components/shared/StatusBadge";
import { Button } from "../components/ui/button";
import { useAuth } from "../context/AuthContext";
import { ExportConfirmDialog } from "../components/shared/ExportConfirmDialog";
import { toast } from "sonner";

const prRecords = [
  {
    pr: "PR-2026-1525",
    prDate: "2026-05-18",
    requestor: "Sarah Chen",
    purpose: "Workshop materials and lab consumables",
    grandTotal: "$1,370.00",
    lastUpdate: "2026-05-20 14:18",
    status: "pending",
    lineItems: [
      {
        identityKey: "PR-2026-1525|misc-supplies|MISC-001|Sarah Chen",
        itemDetails: "Miscellaneous supplies for food processing",
        wbs: "MISC-001",
        labGroup: "FCB",
        lab: "General",
        category: "Consumables",
        amount: "$650.00",
        reviewStatus: "pending",
        reviewReason: "Lab is General inside known Lab Group.",
      },
      {
        identityKey: "PR-2026-1525|quality-control|W3-02-05|Sarah Chen",
        itemDetails: "Quality control test strips",
        wbs: "W3-02-05",
        labGroup: "FCB",
        lab: "W3L2 Food Chemistry",
        category: "Consumables",
        amount: "$720.00",
        reviewStatus: "approved",
        reviewReason: "Auto-classified by WBS and lab alias.",
      },
    ],
  },
  {
    pr: "PR-2026-1527",
    prDate: "2026-05-19",
    requestor: "Emily Wong",
    purpose: "Specialized equipment calibration",
    grandTotal: "$1,850.00",
    lastUpdate: "2026-05-21 09:04",
    status: "approved",
    lineItems: [
      {
        identityKey: "PR-2026-1527|calibration|W4-01-12|Emily Wong",
        itemDetails: "Analytical instrument calibration",
        wbs: "W4-01-12",
        labGroup: "EPD",
        lab: "W4L1",
        category: "Maintenance",
        amount: "$1,850.00",
        reviewStatus: "approved",
        reviewReason: "Reviewed and committed.",
      },
    ],
  },
];

export function RecordsPage() {
  const { user } = useAuth();
  const [showExportDialog, setShowExportDialog] = useState(false);
  const [expandedPr, setExpandedPr] = useState<string | null>("PR-2026-1525");

  const filteredRecords = prRecords.filter((record) => {
    if (user?.role === "admin") return true;
    if (user?.role === "teamlead") {
      return record.lineItems.some((line) => user.assignedLabs?.some((lab) => line.lab.includes(lab)));
    }
    if (user?.role === "labic") {
      return record.lineItems.some((line) => user.assignedLabs?.includes(line.lab));
    }
    return false;
  });

  const handleExport = () => {
    toast.success("Export prepared", {
      description: `${filteredRecords.length} PR headers exported with line-item details.`,
    });
  };

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa]">
      <FilterBar
        searchPlaceholder="Search PR, requestor, WBS, item details..."
        filters={[
          {
            label: "Date Range",
            options: [
              { value: "30d", label: "Last 30 days" },
              { value: "90d", label: "Last 90 days" },
              { value: "ytd", label: "Year to date" },
            ],
          },
          {
            label: "Lab Group",
            options: [
              { value: "all", label: "All Lab Groups" },
              { value: "fcb", label: "FCB" },
              { value: "epd", label: "EPD" },
              { value: "general", label: "General" },
            ],
          },
          {
            label: "Category",
            options: [
              { value: "all", label: "All Categories" },
              { value: "general", label: "General" },
              { value: "consumables", label: "Consumables" },
              { value: "supplies", label: "Supplies" },
              { value: "maintenance", label: "Maintenance" },
            ],
          },
        ]}
        showExport
      />

      <div className="p-6">
        <div className="flex items-center justify-between mb-6">
          <div>
            <h2 className="text-2xl font-semibold text-foreground">PR Records</h2>
            <p className="text-sm text-muted-foreground mt-1">
              PR headers expand to show individual line items, WBS codes, classifications, and review reasons.
            </p>
          </div>
          <Button className="bg-[#1e3a8a] hover:bg-[#1e40af] text-white" onClick={() => setShowExportDialog(true)}>
            <FileDown className="h-4 w-4 mr-2" />
            Export
          </Button>
        </div>

        <Card className="bg-white border-border overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full">
              <thead className="bg-[#f8f9fa]">
                <tr className="border-b border-border">
                  <th className="w-10 p-4" />
                  <th className="text-left p-4 text-sm font-medium text-muted-foreground">PR Number</th>
                  <th className="text-left p-4 text-sm font-medium text-muted-foreground">PR Date</th>
                  <th className="text-left p-4 text-sm font-medium text-muted-foreground">Requestor</th>
                  <th className="text-left p-4 text-sm font-medium text-muted-foreground">Purpose</th>
                  <th className="text-right p-4 text-sm font-medium text-muted-foreground">Grand Total</th>
                  <th className="text-left p-4 text-sm font-medium text-muted-foreground">Last Update</th>
                  <th className="text-left p-4 text-sm font-medium text-muted-foreground">Status</th>
                </tr>
              </thead>
              <tbody>
                {filteredRecords.map((record) => {
                  const isExpanded = expandedPr === record.pr;
                  return (
                    <Fragment key={record.pr}>
                      <tr className="border-b border-border hover:bg-[#f8f9fa] transition-colors">
                        <td className="p-4">
                          <button
                            type="button"
                            className="rounded-md p-1 hover:bg-muted"
                            onClick={() => setExpandedPr(isExpanded ? null : record.pr)}
                            aria-label={isExpanded ? "Collapse PR" : "Expand PR"}
                          >
                            {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                          </button>
                        </td>
                        <td className="p-4 text-sm font-medium text-[#1e3a8a]">{record.pr}</td>
                        <td className="p-4 text-sm text-muted-foreground">{record.prDate}</td>
                        <td className="p-4 text-sm text-muted-foreground">{record.requestor}</td>
                        <td className="p-4 text-sm text-muted-foreground max-w-sm truncate">{record.purpose}</td>
                        <td className="p-4 text-sm text-right font-medium text-foreground">{record.grandTotal}</td>
                        <td className="p-4 text-sm text-muted-foreground">{record.lastUpdate}</td>
                        <td className="p-4">
                          <StatusBadge status={record.status as "approved" | "pending"}>{record.status}</StatusBadge>
                        </td>
                      </tr>
                      {isExpanded && (
                        <tr className="border-b border-border bg-[#f8f9fa]">
                          <td />
                          <td colSpan={7} className="p-4">
                            <div className="overflow-x-auto rounded-md border border-border bg-white">
                              <table className="w-full">
                                <thead className="bg-[#f8f9fa]">
                                  <tr className="border-b border-border">
                                    <th className="text-left p-3 text-xs font-medium text-muted-foreground">Line Identity</th>
                                    <th className="text-left p-3 text-xs font-medium text-muted-foreground">Item Details</th>
                                    <th className="text-left p-3 text-xs font-medium text-muted-foreground">WBS</th>
                                    <th className="text-left p-3 text-xs font-medium text-muted-foreground">Lab Group</th>
                                    <th className="text-left p-3 text-xs font-medium text-muted-foreground">Lab</th>
                                    <th className="text-left p-3 text-xs font-medium text-muted-foreground">Category</th>
                                    <th className="text-right p-3 text-xs font-medium text-muted-foreground">Amount + GST</th>
                                    <th className="text-left p-3 text-xs font-medium text-muted-foreground">Review</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {record.lineItems.map((line) => (
                                    <tr key={line.identityKey} className="border-b border-border last:border-0">
                                      <td className="p-3 text-xs text-muted-foreground max-w-[220px] truncate">{line.identityKey}</td>
                                      <td className="p-3 text-sm text-foreground">{line.itemDetails}</td>
                                      <td className="p-3 text-sm text-muted-foreground">{line.wbs}</td>
                                      <td className="p-3">
                                        <StatusBadge status={line.labGroup === "General" ? "general" : "info"}>{line.labGroup}</StatusBadge>
                                      </td>
                                      <td className="p-3">
                                        <StatusBadge status={line.lab === "General" ? "general" : "info"}>{line.lab}</StatusBadge>
                                      </td>
                                      <td className="p-3">
                                        <StatusBadge status={line.category === "General" ? "general" : "info"}>{line.category}</StatusBadge>
                                      </td>
                                      <td className="p-3 text-right text-sm font-medium text-foreground">{line.amount}</td>
                                      <td className="p-3">
                                        <p className="text-xs text-muted-foreground">{line.reviewReason}</p>
                                      </td>
                                    </tr>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          </td>
                        </tr>
                      )}
                    </Fragment>
                  );
                })}
              </tbody>
            </table>
          </div>
        </Card>

        <ExportConfirmDialog
          open={showExportDialog}
          onOpenChange={setShowExportDialog}
          recordCount={filteredRecords.length}
          onConfirm={handleExport}
        />
      </div>
    </div>
  );
}
