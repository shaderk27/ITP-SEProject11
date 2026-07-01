import { Fragment, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { Card } from "../components/ui/card";
import { FilterBar } from "../components/shared/FilterBar";
import { DatePickerField } from "../components/shared/DatePickerField";
import { StatusBadge } from "../components/shared/StatusBadge";
import { Button } from "../components/ui/button";
import { useAuth } from "../context/AuthContext";
import { ExportConfirmDialog } from "../components/shared/ExportConfirmDialog";
import { toast } from "sonner";
import { listCommittedPRs } from "../services/recordsService";
import type { CommittedPR } from "../types/records";

export function RecordsPage() {
  const { user } = useAuth();

  const [records, setRecords] = useState<CommittedPR[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [showExportDialog, setShowExportDialog] = useState(false);
  const [expandedPr, setExpandedPr] = useState<number | null>(null);
  const [searchQuery, setSearchQuery] = useState("");
  const [labGroupFilter, setLabGroupFilter] = useState("all");
  const [dateRange, setDateRange] = useState("all");
  // Custom date range (overrides the preset when either is set).
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const customActive = Boolean(startDate || endDate);

  const fetchRecords = async (
    range: string = dateRange,
    start: string = startDate,
    end: string = endDate,
  ) => {
    setLoading(true);
    setError(null);
    try {
      const data = await listCommittedPRs(range, start, end);
      setRecords(data);
      if (data.length > 0 && expandedPr === null) {
        setExpandedPr(data[0].pr_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load PR records.");
      setRecords([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchRecords(dateRange, startDate, endDate);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.email, dateRange, startDate, endDate]);

  const handleExport = () => {
    // Real CSV/Excel export is future work; for now confirm the click.
    toast.success("Export prepared", {
      description: `${records.length} PR record${records.length === 1 ? "" : "s"} ready (export wiring is a future step).`,
    });
    setShowExportDialog(false);
  };

  // Lab Group options pulled from current data so the filter chip reflects reality.
  const labGroupOptions = Array.from(
    new Set(records.map((r) => r.lab_group_name)),
  ).map((name) => ({ value: name.toLowerCase(), label: name }));

  const q = searchQuery.trim().toLowerCase();
  const filteredRecords = records.filter((pr) => {
    // Lab Group dropdown filter (option value is the lowercased group name).
    if (
      labGroupFilter !== "all" &&
      pr.lab_group_name?.toLowerCase() !== labGroupFilter
    ) {
      return false;
    }
    if (!q) return true;
    if (pr.source_pr_number?.toLowerCase().includes(q)) return true;
    if (pr.requestor_name?.toLowerCase().includes(q)) return true;
    if (pr.wbs_code?.toLowerCase().includes(q)) return true;
    if (pr.lab_group_name?.toLowerCase().includes(q)) return true;
    return pr.lines.some(
      (line) =>
        line.item_description?.toLowerCase().includes(q) ||
        line.lab_name?.toLowerCase().includes(q) ||
        line.pr_status?.toLowerCase().includes(q),
    );
  });

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa]">
      <FilterBar
        searchPlaceholder="Search PR, requestor, WBS, status, item details..."
        onSearchChange={setSearchQuery}
        onFilterChange={(filterId, value) => {
          if (filterId === "Lab Group") setLabGroupFilter(value);
          if (filterId === "Date Range") {
            // Picking a preset clears any custom range so the preset applies.
            setDateRange(value);
            setStartDate("");
            setEndDate("");
          }
        }}
        filters={[
          {
            label: "Lab Group",
            value: labGroupFilter,
            options: [{ value: "all", label: "All Lab Groups" }, ...labGroupOptions],
          },
          {
            label: "Date Range",
            value: dateRange,
            options: [
              { value: "all", label: "All time" },
              { value: "fy", label: "This fiscal year" },
              { value: "30d", label: "Last 30 days" },
              { value: "90d", label: "Last 90 days" },
              { value: "ytd", label: "Year to date" },
            ],
          },
        ]}
        showExport
        onExport={() => setShowExportDialog(true)}
      />

      {/* Custom date range — overrides the preset when set. */}
      <div className="flex items-center gap-3 px-4 py-3 bg-white border-b border-border text-sm">
        <span className="text-muted-foreground">Custom range:</span>
        <label className="flex items-center gap-1.5">
          <span className="text-muted-foreground">From</span>
          <DatePickerField
            value={startDate}
            maxDate={endDate || undefined}
            onChange={setStartDate}
          />
        </label>
        <label className="flex items-center gap-1.5">
          <span className="text-muted-foreground">To</span>
          <DatePickerField
            value={endDate}
            minDate={startDate || undefined}
            onChange={setEndDate}
          />
        </label>
        {customActive && (
          <>
            <span className="text-xs text-blue-600">
              Custom range active — preset ignored
            </span>
            <Button
              variant="outline"
              size="sm"
              onClick={() => {
                setStartDate("");
                setEndDate("");
              }}
            >
              Clear
            </Button>
          </>
        )}
      </div>

      <div className="p-6">
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold text-foreground">PR Records</h2>
            <p className="text-sm text-muted-foreground mt-1">
              {loading
                ? "Loading…"
                : q
                  ? `${filteredRecords.length} of ${records.length} committed purchase request${records.length === 1 ? "" : "s"} match "${searchQuery.trim()}".`
                  : labGroupFilter !== "all"
                    ? `${filteredRecords.length} of ${records.length} committed purchase request${records.length === 1 ? "" : "s"} shown.`
                    : `${records.length} committed purchase request${records.length === 1 ? "" : "s"}.`}
            </p>
          </div>
          <Button size="sm" variant="outline" onClick={() => fetchRecords()} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-1 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>

        {error && (
          <Card className="p-4 mb-4 bg-[#fef2f2] border-[#fecaca]">
            <p className="text-sm text-[#b91c1c]">{error}</p>
          </Card>
        )}

        {!loading && !error && records.length === 0 && (
          <Card className="p-8 text-center text-muted-foreground">
            <p className="text-sm">
              No committed purchase requests yet. Upload a file, resolve any review items, and commit the batch — committed PRs appear here.
            </p>
          </Card>
        )}

        {!loading && !error && records.length > 0 && filteredRecords.length === 0 && (
          <Card className="p-8 text-center text-muted-foreground">
            <p className="text-sm">
              No PRs match "{searchQuery.trim()}". Try a different search term.
            </p>
          </Card>
        )}

        <div className="space-y-4">
          {filteredRecords.map((pr) => {
            const isExpanded = expandedPr === pr.pr_id;
            return (
              <Card key={pr.pr_id} className="bg-white border-border overflow-hidden">
                <button
                  type="button"
                  className="w-full p-5 flex items-center justify-between gap-4 text-left hover:bg-[#f8f9fa]"
                  onClick={() => setExpandedPr(isExpanded ? null : pr.pr_id)}
                >
                  <div className="flex items-center gap-3 min-w-0 flex-1">
                    {isExpanded ? <ChevronDown className="h-5 w-5 shrink-0" /> : <ChevronRight className="h-5 w-5 shrink-0" />}
                    <div className="min-w-0">
                      <div className="flex items-center gap-2 flex-wrap">
                        <p className="text-lg font-semibold text-foreground">{pr.source_pr_number}</p>
                        <StatusBadge status="approved">{prettyStatus(pr.status)}</StatusBadge>
                        <StatusBadge status="info">{pr.lab_group_name}</StatusBadge>
                      </div>
                      <p className="text-sm text-muted-foreground mt-1 truncate">
                        {pr.requestor_name || "Unknown"} · {pr.purpose || "—"}
                      </p>
                      <p className="text-xs text-muted-foreground mt-1">
                        WBS: {pr.wbs_code || "—"} · Last update: {formatDate(pr.updated_at)}
                        {pr.latest_batch_id ? ` · Batch #${pr.latest_batch_id}` : ""}
                      </p>
                    </div>
                  </div>
                  <div className="text-right shrink-0">
                    <p className="text-lg font-semibold text-foreground">${formatAmount(pr.grand_total_sgd)}</p>
                    <p className="text-xs text-muted-foreground">{pr.lines.length} line{pr.lines.length === 1 ? "" : "s"}</p>
                  </div>
                </button>

                {isExpanded && (
                  <div className="border-t border-border overflow-x-auto">
                    <table className="w-full">
                      <thead className="bg-[#f8f9fa]">
                        <tr className="border-b border-border">
                          <th className="text-left p-3 text-xs font-medium text-muted-foreground">Line</th>
                          <th className="text-left p-3 text-xs font-medium text-muted-foreground">Item</th>
                          <th className="text-left p-3 text-xs font-medium text-muted-foreground">Lab</th>
                          <th className="text-left p-3 text-xs font-medium text-muted-foreground">Category</th>
                          <th className="text-left p-3 text-xs font-medium text-muted-foreground">PR Date</th>
                          <th className="text-right p-3 text-xs font-medium text-muted-foreground">Qty</th>
                          <th className="text-right p-3 text-xs font-medium text-muted-foreground">Unit Rate</th>
                          <th className="text-right p-3 text-xs font-medium text-muted-foreground">Amount + GST</th>
                          <th className="text-left p-3 text-xs font-medium text-muted-foreground">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pr.lines.map((line) => (
                          <Fragment key={line.pr_line_id}>
                            <tr className="border-b border-border last:border-0 hover:bg-[#f8f9fa]">
                              <td className="p-3 text-sm font-medium text-foreground">
                                Line {line.line_no ?? "—"}
                              </td>
                              <td className="p-3 text-sm text-foreground">{line.item_description || "—"}</td>
                              <td className="p-3 text-sm text-muted-foreground">{line.lab_name}</td>
                              <td className="p-3 text-sm text-muted-foreground">{line.category_name}</td>
                              <td className="p-3 text-sm text-muted-foreground">
                                {pr.request_date ? formatDateOnly(pr.request_date) : "—"}
                              </td>
                              <td className="p-3 text-sm text-right text-muted-foreground">
                                {line.qty ?? "—"}
                              </td>
                              <td className="p-3 text-sm text-right text-muted-foreground">
                                {line.unit_rate ? `$${formatAmount(line.unit_rate)}` : "—"}
                              </td>
                              <td className="p-3 text-sm text-right font-medium text-foreground">
                                {line.currency_code === "SGD" ? "$" : `${line.currency_code} `}
                                {formatAmount(line.amount_gst)}
                              </td>
                              <td className="p-3 text-sm">
                                {line.pr_status ? (
                                  <StatusBadge status={prStatusVariant(line.pr_status)}>
                                    {line.pr_status}
                                  </StatusBadge>
                                ) : (
                                  <span className="text-xs text-muted-foreground">—</span>
                                )}
                              </td>
                            </tr>
                          </Fragment>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
            );
          })}
        </div>
      </div>

      <ExportConfirmDialog
        open={showExportDialog}
        onOpenChange={setShowExportDialog}
        onConfirm={handleExport}
        recordCount={records.length}
      />
    </div>
  );
}

function formatDate(iso: string): string {
  try {
    const d = new Date(iso);
    return d.toLocaleString(undefined, {
      year: "numeric",
      month: "short",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return iso;
  }
}

// Date-only formatter for PR Sub Date. Parses the yyyy-mm-dd parts as a local
// date so a UTC-midnight ISO string never shifts to the previous day.
function formatDateOnly(iso: string): string {
  const [y, m, d] = iso.slice(0, 10).split("-").map(Number);
  if (!y || !m || !d) return iso;
  return new Date(y, m - 1, d).toLocaleDateString(undefined, {
    year: "numeric",
    month: "short",
    day: "2-digit",
  });
}

function formatAmount(raw: string): string {
  const num = Number(raw);
  if (Number.isNaN(num)) return raw;
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}

function prettyStatus(raw: string): string {
  return raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

// Maps the source-system PR Status string to a StatusBadge variant.
// Raw text is displayed as-is; this only picks the color.
function prStatusVariant(raw: string): "approved" | "pending" | "rejected" | "general" {
  const lower = raw.toLowerCase();
  if (lower.startsWith("approved")) return "approved";
  if (lower.startsWith("rejected")) return "rejected";
  if (lower.startsWith("pending")) return "pending";
  return "general";
}
