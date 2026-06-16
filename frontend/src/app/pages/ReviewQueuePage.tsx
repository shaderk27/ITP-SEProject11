import { Fragment, useState } from "react";
import { Link } from "react-router";
import { ChevronDown, ChevronRight, Eye, Lock } from "lucide-react";
import { Card } from "../components/ui/card";
import { FilterBar } from "../components/shared/FilterBar";
import { StatusBadge } from "../components/shared/StatusBadge";
import { Button } from "../components/ui/button";

const reviewBatches = [
  {
    batchId: "UP-2026-053",
    owner: "Sarah Chen",
    uploadedAt: "2026-05-20 14:18",
    status: "Review Required",
    prs: [
      {
        pr: "PR-2026-1525",
        requestor: "Sarah Chen",
        purpose: "Workshop materials and lab consumables",
        lines: [
          {
            id: "REV-001",
            line: "Line 3",
            itemDetails: "Miscellaneous supplies for food processing unit",
            wbs: "MISC-001",
            labGroup: "FCB",
            lab: "General",
            category: "Consumables",
            amount: "$650.00",
            issue: "Lab is General because no configured lab alias matched purpose, vendor instruction, or requester mapping.",
          },
        ],
      },
      {
        pr: "PR-2026-1526",
        requestor: "Michael Tan",
        purpose: "External testing service for material samples",
        lines: [
          {
            id: "REV-002",
            line: "Line 1",
            itemDetails: "External testing service",
            wbs: "W3-99-01",
            labGroup: "General",
            lab: "General",
            category: "Services",
            amount: "$3,200.00",
            issue: "WBS did not map confidently to a Lab Group. This line must be reviewed before budget calculation.",
          },
          {
            id: "REV-003",
            line: "Line 2",
            itemDetails: "Specialized equipment calibration",
            wbs: "W4-01-12",
            labGroup: "EPD",
            lab: "W4L1",
            category: "General",
            amount: "$1,850.00",
            issue: "Category is General because uploaded PR category did not match configured presets.",
          },
        ],
      },
    ],
  },
  {
    batchId: "UP-2026-052",
    owner: "Emily Wong",
    uploadedAt: "2026-05-19 09:04",
    status: "Review Required",
    prs: [
      {
        pr: "PR-2026-1519",
        requestor: "Emily Wong",
        purpose: "Replacement consumables for tensile testing",
        lines: [
          {
            id: "REV-004",
            line: "Line 1",
            itemDetails: "Consumable replacement pack",
            wbs: "W4-01-12",
            labGroup: "EPD",
            lab: "W4L1",
            category: "General",
            amount: "$920.00",
            issue: "Category fallback requires Team Lead confirmation.",
          },
        ],
      },
    ],
  },
];

export function ReviewQueuePage() {
  const [expandedBatch, setExpandedBatch] = useState<string | null>("UP-2026-053");
  const [expandedPr, setExpandedPr] = useState<string | null>("PR-2026-1525");

  const totalLines = reviewBatches.reduce(
    (batchTotal, batch) => batchTotal + batch.prs.reduce((prTotal, pr) => prTotal + pr.lines.length, 0),
    0
  );

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa]">
      <FilterBar
        searchPlaceholder="Search batch, PR, line item, WBS, requestor..."
        filters={[
          {
            label: "Upload Batch",
            options: [
              { value: "all", label: "All Batches" },
              { value: "UP-2026-053", label: "UP-2026-053" },
              { value: "UP-2026-052", label: "UP-2026-052" },
            ],
          },
          {
            label: "Review Reason",
            options: [
              { value: "all", label: "All Reasons" },
              { value: "lab-group", label: "Lab Group General" },
              { value: "lab", label: "Lab General" },
              { value: "category", label: "Category General" },
            ],
          },
        ]}
        showExport
      />

      <div className="p-6">
        <div className="mb-6">
          <h2 className="text-2xl font-semibold text-foreground">Review Queue</h2>
          <p className="text-sm text-muted-foreground mt-1">
            {totalLines} unresolved line errors across {reviewBatches.length} upload batches.
          </p>
        </div>

        <Card className="p-4 bg-[#fff7ed] border-[#fed7aa] mb-6">
          <div className="flex items-start gap-3">
            <Lock className="h-5 w-5 text-[#c2410c] mt-0.5" />
            <div>
              <p className="text-sm font-medium text-[#9a3412]">
                Expand a batch, then expand a PR to edit its individual error lines.
              </p>
              <p className="text-sm text-[#9a3412] mt-1">
                A batch can only be approved or committed after every listed line error in that batch is resolved.
              </p>
            </div>
          </div>
        </Card>

        <div className="space-y-4">
          {reviewBatches.map((batch) => {
            const batchLineCount = batch.prs.reduce((total, pr) => total + pr.lines.length, 0);
            const isBatchExpanded = expandedBatch === batch.batchId;

            return (
              <Card key={batch.batchId} className="bg-white border-border overflow-hidden">
                <button
                  type="button"
                  className="w-full p-5 flex items-center justify-between gap-4 text-left hover:bg-[#f8f9fa]"
                  onClick={() => setExpandedBatch(isBatchExpanded ? null : batch.batchId)}
                >
                  <div className="flex items-center gap-3">
                    {isBatchExpanded ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
                    <div>
                      <p className="text-lg font-semibold text-foreground">{batch.batchId}</p>
                      <p className="text-sm text-muted-foreground">
                        {batchLineCount} unresolved line errors - Owner: {batch.owner} - Uploaded {batch.uploadedAt}
                      </p>
                    </div>
                  </div>
                  <StatusBadge status="pending">{batch.status}</StatusBadge>
                </button>

                {isBatchExpanded && (
                  <div className="border-t border-border bg-[#f8f9fa] p-4 space-y-3">
                    {batch.prs.map((pr) => {
                      const isPrExpanded = expandedPr === pr.pr;
                      return (
                        <div key={pr.pr} className="rounded-md border border-border bg-white overflow-hidden">
                          <button
                            type="button"
                            className="w-full p-4 flex items-center justify-between gap-4 text-left hover:bg-[#f8f9fa]"
                            onClick={() => setExpandedPr(isPrExpanded ? null : pr.pr)}
                          >
                            <div className="flex items-center gap-3">
                              {isPrExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
                              <div>
                                <p className="text-sm font-semibold text-foreground">{pr.pr}</p>
                                <p className="text-xs text-muted-foreground">
                                  {pr.lines.length} line error{pr.lines.length === 1 ? "" : "s"} - {pr.requestor}
                                </p>
                              </div>
                            </div>
                            <StatusBadge status="warning">Needs line edits</StatusBadge>
                          </button>

                          {isPrExpanded && (
                            <div className="border-t border-border overflow-x-auto">
                              <table className="w-full">
                                <thead className="bg-[#f8f9fa]">
                                  <tr className="border-b border-border">
                                    <th className="text-left p-3 text-xs font-medium text-muted-foreground">Line</th>
                                    <th className="text-left p-3 text-xs font-medium text-muted-foreground">Item</th>
                                    <th className="text-left p-3 text-xs font-medium text-muted-foreground">WBS</th>
                                    <th className="text-left p-3 text-xs font-medium text-muted-foreground">Current Classification</th>
                                    <th className="text-left p-3 text-xs font-medium text-muted-foreground">Issue</th>
                                    <th className="text-right p-3 text-xs font-medium text-muted-foreground">Amount + GST</th>
                                    <th className="text-center p-3 text-xs font-medium text-muted-foreground">Action</th>
                                  </tr>
                                </thead>
                                <tbody>
                                  {pr.lines.map((line) => (
                                    <Fragment key={line.id}>
                                      <tr className="border-b border-border last:border-0 hover:bg-[#f8f9fa]">
                                        <td className="p-3 text-sm font-medium text-foreground">{line.line}</td>
                                        <td className="p-3 text-sm text-foreground">{line.itemDetails}</td>
                                        <td className="p-3 text-sm text-muted-foreground">{line.wbs}</td>
                                        <td className="p-3">
                                          <div className="flex flex-wrap gap-2">
                                            <StatusBadge status={line.labGroup === "General" ? "general" : "info"}>{line.labGroup}</StatusBadge>
                                            <StatusBadge status={line.lab === "General" ? "general" : "info"}>{line.lab}</StatusBadge>
                                            <StatusBadge status={line.category === "General" ? "general" : "info"}>{line.category}</StatusBadge>
                                          </div>
                                        </td>
                                        <td className="p-3 text-xs text-muted-foreground max-w-sm">{line.issue}</td>
                                        <td className="p-3 text-sm text-right font-medium text-foreground">{line.amount}</td>
                                        <td className="p-3 text-center">
                                          <Link to={`/review/${line.id}`}>
                                            <Button size="sm" variant="outline">
                                              <Eye className="h-4 w-4 mr-1" />
                                              Edit Line
                                            </Button>
                                          </Link>
                                        </td>
                                      </tr>
                                    </Fragment>
                                  ))}
                                </tbody>
                              </table>
                            </div>
                          )}
                        </div>
                      );
                    })}
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      </div>
    </div>
  );
}
