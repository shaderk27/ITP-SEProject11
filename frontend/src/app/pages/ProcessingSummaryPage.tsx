import { CheckCircle, AlertTriangle, Info, XCircle, RefreshCw } from "lucide-react";
import { Link, useLocation } from "react-router";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "../components/ui/tabs";
import { StatusBadge } from "../components/shared/StatusBadge";
import { DuplicateWarning } from "../components/shared/DuplicateWarning";
import { SystemNotification } from "../components/shared/SystemNotification";
import type { UploadProcessResult } from "../types/upload";

const uploadResult = {
  totalLines: 152,
  accepted: 98,
  duplicateSkipped: 5,
  reuploadUpdated: 12,
  needsReview: 28,
  rejected: 9,
};

const sampleLines = {
  accepted: [
    { pr: "PR-2026-1523", line: "Line 1", item: "Lab equipment maintenance", wbs: "W3-01-08", labGroup: "FCB", lab: "W3L1 Food PP", category: "Maintenance", amount: "$2,450" },
    { pr: "PR-2026-1524", line: "Line 2", item: "Chemical supplies order", wbs: "W4-02-15", labGroup: "EPD", lab: "W4L2", category: "Consumables", amount: "$890" },
  ],
  updates: [
    { pr: "PR-2026-1401", line: "Line 1", identity: "PR + item details + WBS + requestor", changed: "Amount + GST changed from $1,120 to $1,200", amount: "$1,200" },
  ],
  duplicates: [
    { pr: "PR-2026-1430", line: "Line 4", identity: "Same line identity and same content hash", uploadedBefore: "2026-04-30" },
    { pr: "PR-2026-1432", line: "Line 7", identity: "Same line identity and same content hash", uploadedBefore: "2026-05-18" },
  ],
  review: [
    { pr: "PR-2026-1525", line: "Line 3", item: "Miscellaneous supplies", wbs: "MISC-001", issue: "Lab is General inside FCB", amount: "$650" },
    { pr: "PR-2026-1526", line: "Line 1", item: "External testing service", wbs: "W3-99-01", issue: "Lab Group is General", amount: "$3,200" },
  ],
  rejected: [
    { row: 45, pr: "PR-2026-XXXX", issue: "Missing required WBS field" },
    { row: 72, pr: "PR-2026-1431", issue: "Invalid amount value" },
  ],
};

export function ProcessingSummaryPage() {
  const location = useLocation();
  const result = (location.state as { uploadResult?: UploadProcessResult } | null)?.uploadResult;
  const displayCounts = result
    ? {
        totalLines: result.counts.total_lines,
        accepted: result.counts.accepted,
        duplicateSkipped: result.counts.duplicate_skipped,
        reuploadUpdated: result.counts.reupload_updated,
        needsReview: result.counts.needs_review,
        rejected: result.counts.rejected,
      }
    : uploadResult;
  const acceptedRows = result
    ? result.records.inserted.map((record) => [
        record.line.pr_number,
        `Row ${record.line.row_number}`,
        record.line.item_details,
        record.line.wbs,
        record.line.lab_group || "Pending Mapping",
        record.line.lab || "General",
        record.line.pr_category || "General",
        record.line.amount_gst,
      ])
    : sampleLines.accepted.map((line) => [
        line.pr,
        line.line,
        line.item,
        line.wbs,
        line.labGroup,
        line.lab,
        line.category,
        line.amount,
      ]);
  const updateRows = result
    ? result.records.updated.map((record) => [
        record.line.pr_number,
        `Row ${record.line.row_number}`,
        "PR + item details + WBS + requestor + purpose",
        record.reason,
        record.line.amount_gst,
      ])
    : sampleLines.updates.map((line) => [line.pr, line.line, line.identity, line.changed, line.amount]);
  const duplicateRows = result
    ? result.records.duplicate.map((record) => [
        record.line.pr_number,
        `Row ${record.line.row_number}`,
        record.reason,
        record.previous_batch_id ?? "Previous upload",
      ])
    : sampleLines.duplicates.map((line) => [line.pr, line.line, line.identity, line.uploadedBefore]);
  const rejectedRows = result
    ? result.validation_errors.map((error, index) => ({
        row: index + 1,
        pr: error.field,
        issue: error.message,
      }))
    : sampleLines.rejected;

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa]">
      <div className="p-6 space-y-6">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-2xl font-semibold text-foreground mb-2">Upload Processing Summary</h2>
            <p className="text-sm text-muted-foreground">
              Upload ID: {result?.metadata.batch_id ?? "UP-2026-053"} - Processed {result?.metadata.uploaded_at ?? "on 2026-05-23"}
            </p>
          </div>
          <Link to="/upload">
            <Button variant="outline">Upload Another File</Button>
          </Link>
        </div>

        <SystemNotification
          type="success"
          title="File Processing Complete"
          message="Uploaded rows were parsed as PR line items. Lines with unresolved Lab Group, Lab, or Category values are held for review."
        />

        <DuplicateWarning count={displayCounts.duplicateSkipped + displayCounts.reuploadUpdated} />

        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-6 gap-4">
          <Card className="p-5 bg-white border-border">
            <Info className="h-5 w-5 text-[#2563eb] mb-3" />
            <p className="text-2xl font-semibold text-foreground">{displayCounts.totalLines}</p>
            <p className="text-xs text-muted-foreground">Total Lines</p>
          </Card>
          <Card className="p-5 bg-white border-border">
            <CheckCircle className="h-5 w-5 text-[#059669] mb-3" />
            <p className="text-2xl font-semibold text-foreground">{displayCounts.accepted}</p>
            <p className="text-xs text-muted-foreground">Accepted</p>
          </Card>
          <Card className="p-5 bg-white border-border">
            <Info className="h-5 w-5 text-[#2563eb] mb-3" />
            <p className="text-2xl font-semibold text-foreground">{displayCounts.duplicateSkipped}</p>
            <p className="text-xs text-muted-foreground">Duplicate Skipped</p>
          </Card>
          <Card className="p-5 bg-white border-border">
            <RefreshCw className="h-5 w-5 text-[#7c3aed] mb-3" />
            <p className="text-2xl font-semibold text-foreground">{displayCounts.reuploadUpdated}</p>
            <p className="text-xs text-muted-foreground">Reupload Updated</p>
          </Card>
          <Card className="p-5 bg-white border-border">
            <AlertTriangle className="h-5 w-5 text-[#d97706] mb-3" />
            <p className="text-2xl font-semibold text-foreground">{displayCounts.needsReview}</p>
            <p className="text-xs text-muted-foreground">Needs Review</p>
          </Card>
          <Card className="p-5 bg-white border-border">
            <XCircle className="h-5 w-5 text-[#dc2626] mb-3" />
            <p className="text-2xl font-semibold text-foreground">{displayCounts.rejected}</p>
            <p className="text-xs text-muted-foreground">Rejected</p>
          </Card>
        </div>

        <Card className="bg-white border-border">
          <Tabs defaultValue="accepted" className="w-full">
            <div className="border-b border-border">
              <TabsList className="w-full justify-start rounded-none bg-transparent h-auto p-0">
                <TabsTrigger value="accepted" className="rounded-none data-[state=active]:border-b-2 data-[state=active]:border-[#1e3a8a]">
                  Accepted ({displayCounts.accepted})
                </TabsTrigger>
                <TabsTrigger value="updates" className="rounded-none data-[state=active]:border-b-2 data-[state=active]:border-[#1e3a8a]">
                  Reupload Updates ({displayCounts.reuploadUpdated})
                </TabsTrigger>
                <TabsTrigger value="duplicates" className="rounded-none data-[state=active]:border-b-2 data-[state=active]:border-[#1e3a8a]">
                  Duplicate Skips ({displayCounts.duplicateSkipped})
                </TabsTrigger>
                <TabsTrigger value="review" className="rounded-none data-[state=active]:border-b-2 data-[state=active]:border-[#1e3a8a]">
                  Needs Review ({displayCounts.needsReview})
                </TabsTrigger>
                <TabsTrigger value="rejected" className="rounded-none data-[state=active]:border-b-2 data-[state=active]:border-[#1e3a8a]">
                  Rejected ({displayCounts.rejected})
                </TabsTrigger>
              </TabsList>
            </div>

            <TabsContent value="accepted" className="p-6">
              <SummaryTable
                columns={["PR", "Line", "Item", "WBS", "Lab Group", "Lab", "Category", "Amount + GST"]}
                rows={acceptedRows}
              />
            </TabsContent>

            <TabsContent value="updates" className="p-6">
              <SummaryTable
                columns={["PR", "Line", "Identity Basis", "Detected Change", "Latest Amount"]}
                rows={updateRows}
              />
            </TabsContent>

            <TabsContent value="duplicates" className="p-6">
              <SummaryTable
                columns={["PR", "Line", "Reason", "Previously Uploaded"]}
                rows={duplicateRows}
              />
            </TabsContent>

            <TabsContent value="review" className="p-6">
              <SummaryTable
                columns={["PR", "Line", "Item", "WBS", "Review Issue", "Amount + GST"]}
                rows={sampleLines.review.map((line) => [line.pr, line.line, line.item, line.wbs, line.issue, line.amount])}
              />
            </TabsContent>

            <TabsContent value="rejected" className="p-6">
              <div className="space-y-3">
                {rejectedRows.map((error) => (
                  <div key={`${error.row}-${error.pr}`} className="flex items-start gap-3 p-4 bg-[#fef2f2] rounded-lg border border-[#fecaca]">
                    <XCircle className="h-5 w-5 text-[#dc2626] mt-0.5" />
                    <div className="flex-1">
                      <p className="text-sm font-medium text-[#dc2626]">Row {error.row}: {error.pr}</p>
                      <p className="text-sm text-[#991b1b] mt-1">{error.issue}</p>
                    </div>
                  </div>
                ))}
              </div>
            </TabsContent>
          </Tabs>
        </Card>

        <div className="flex justify-end gap-4">
          <Link to="/review">
            <Button className="bg-[#1e3a8a] hover:bg-[#1e40af] text-white">
              Review Pending Lines
            </Button>
          </Link>
          <Link to="/">
            <Button variant="outline">Back to Dashboard</Button>
          </Link>
        </div>
      </div>
    </div>
  );
}

function SummaryTable({ columns, rows }: { columns: string[]; rows: string[][] }) {
  return (
    <div className="overflow-x-auto">
      <table className="w-full">
        <thead className="bg-[#f8f9fa]">
          <tr className="border-b border-border">
            {columns.map((column) => (
              <th key={column} className="text-left p-3 text-sm font-medium text-muted-foreground">
                {column}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((row) => (
            <tr key={row.join("|")} className="border-b border-border last:border-0 hover:bg-[#f8f9fa]">
              {row.map((cell, index) => (
                <td key={`${cell}-${index}`} className="p-3 text-sm text-muted-foreground">
                  {isClassificationCell(cell) ? <StatusBadge status={cell === "General" ? "general" : "info"}>{cell}</StatusBadge> : cell}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function isClassificationCell(value: string) {
  return ["FCB", "EPD", "General", "W3L1 Food PP", "W4L2", "Consumables", "Maintenance"].includes(value);
}
