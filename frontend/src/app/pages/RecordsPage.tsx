import { Fragment, useEffect, useState } from "react";
import { ChevronDown, ChevronRight, RefreshCw } from "lucide-react";
import { Card } from "../components/ui/card";
import { FilterBar } from "../components/shared/FilterBar";
import { MonthRangePicker } from "../components/shared/MonthRangePicker";
import { StatusBadge } from "../components/shared/StatusBadge";
import { Button } from "../components/ui/button";
import { useAuth } from "../context/AuthContext";
import { ExportConfirmDialog } from "../components/shared/ExportConfirmDialog";
import { toast } from "sonner";
import { exportCommittedPRs, listCommittedPRs } from "../services/recordsService";
import { listPeriods, type Period } from "../services/dashboardService";
import { format } from "date-fns";
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
  // Fiscal year is the master time scope; the presets/custom narrow within it.
  const [periods, setPeriods] = useState<Period[]>([]);
  const [selectedFYPeriodId, setSelectedFYPeriodId] = useState<number | null>(null);
  const [dateRange, setDateRange] = useState("all");
  // Custom month range (overrides the preset when either is set): startDate is
  // the 1st of the From month, endDate the last day of the To month.
  const [startDate, setStartDate] = useState("");
  const [endDate, setEndDate] = useState("");
  const customActive = Boolean(startDate || endDate);
  const selectedPeriod = periods.find((p) => p.id === selectedFYPeriodId);

  // Effective request window: the selected fiscal year's Apr–Mar span,
  // narrowed by the custom range (if set) or the preset. Shared by the list
  // fetch and the export so the downloaded file covers the same window.
  const effectiveRange = (): { effStart: string; effEnd: string } => {
    // Base window = the selected fiscal year's Apr–Mar span.
    const period = periods.find((p) => p.id === selectedFYPeriodId);
    const fyStart = period?.start_date ?? "";
    const fyEnd = period?.end_date ?? "";
    // Optional sub-window: custom range wins, else a preset.
    let rawStart = "";
    let rawEnd = "";
    if (startDate || endDate) {
      rawStart = startDate;
      rawEnd = endDate;
    } else if (dateRange === "ytd") {
      rawStart = `${new Date().getFullYear()}-01-01`;
      rawEnd = format(new Date(), "yyyy-MM-dd");
    }
    // Clamp the sub-window to the FY span (ISO dates sort lexicographically).
    return {
      effStart: !rawStart ? fyStart : rawStart > fyStart ? rawStart : fyStart,
      effEnd: !rawEnd ? fyEnd : !fyEnd || rawEnd < fyEnd ? rawEnd : fyEnd,
    };
  };

  const fetchRecords = async () => {
    setLoading(true);
    setError(null);
    try {
      const { effStart, effEnd } = effectiveRange();
      const data = await listCommittedPRs("all", effStart, effEnd);
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

  // Load fiscal years once; default to the newest (current FY).
  useEffect(() => {
    listPeriods()
      .then((data) => {
        setPeriods(data);
        if (data.length) setSelectedFYPeriodId(data[0].id);
      })
      .catch(() => {});
  }, []);

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchRecords();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.email, selectedFYPeriodId, dateRange, startDate, endDate, periods]);

  // Download exactly what the page is showing. The date window and the
  // search / Lab Group filters all go to the server, which re-applies this
  // user's role scoping before building the workbook. Throws on failure so
  // the dialog can stay open for a retry.
  const handleExport = async () => {
    const { effStart, effEnd } = effectiveRange();
    try {
      const filename = await exportCommittedPRs({
        startDate: effStart,
        endDate: effEnd,
        dateRange,
        search: searchQuery,
        // Only Admin has the Lab Group dropdown; the others are already
        // scoped server-side, so never send a stale value for them.
        labGroup: user?.role === "admin" ? labGroupFilter : "all",
        periodId: selectedFYPeriodId,
        customStart: startDate,
        customEnd: endDate,
      });
      toast.success("Export complete", {
        description: `${filename} — ${filteredRecords.length} PR record${filteredRecords.length === 1 ? "" : "s"} saved to your downloads folder.`,
      });
      setShowExportDialog(false);
    } catch (err) {
      toast.error("Export failed", {
        description:
          err instanceof Error ? err.message : "Could not generate the report.",
      });
      throw err;
    }
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
          if (filterId === "Fiscal Year") {
            const id = value === "all" ? 0 : Number(value);
            setSelectedFYPeriodId(id);
            // Drop a custom range that falls outside the new year rather than
            // silently clamping it into an empty or partial window.
            const next = periods.find((p) => p.id === id);
            const inYear = (d: string) =>
              !next || !d || (next.start_date <= d && d <= next.end_date);
            if (!inYear(startDate) || !inYear(endDate)) {
              setStartDate("");
              setEndDate("");
            }
          }
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
            label: "Fiscal Year",
            value:
              selectedFYPeriodId == null
                ? ""
                : selectedFYPeriodId === 0
                  ? "all"
                  : String(selectedFYPeriodId),
            options: [
              { value: "all", label: "All time" },
              ...periods.map((p) => ({ value: String(p.id), label: p.name })),
            ],
          },
          // Only Admin sees every lab group; Team Lead is scoped to one group
          // and Lab IC to one lab, so the Lab Group filter is meaningless for
          // them — hide it for both.
          ...(user?.role === "admin"
            ? [
                {
                  label: "Lab Group",
                  value: labGroupFilter,
                  options: [
                    { value: "all", label: "All Lab Groups" },
                    ...labGroupOptions,
                  ],
                },
              ]
            : []),
          {
            label: "Date Range",
            value: dateRange,
            options: [
              { value: "all", label: "Whole year" },
              { value: "ytd", label: "Year to date" },
            ],
          },
        ]}
        showExport
        onExport={() => setShowExportDialog(true)}
      />

      {/* Custom month range — overrides the preset when set. */}
      <div className="flex items-center gap-3 px-4 py-3 bg-white border-b border-border text-sm">
        <span className="text-muted-foreground">Custom range:</span>
        <MonthRangePicker
          periods={selectedPeriod ? [selectedPeriod] : periods}
          startDate={startDate}
          endDate={endDate}
          onStartChange={setStartDate}
          onEndChange={setEndDate}
        />
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
              <Card key={pr.pr_id} className="bg-white border-[#cbd5e1] overflow-hidden">
                <button
                  type="button"
                  className={`w-full p-5 flex items-center justify-between gap-4 text-left ${
                    isExpanded ? "bg-[#e2e8f0]" : "hover:bg-[#f1f5f9]"
                  }`}
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
                  <div className="border-t border-[#cbd5e1] overflow-x-auto">
                    <table className="w-full">
                      <thead className="bg-[#e2e8f0]">
                        <tr className="border-b border-[#cbd5e1]">
                          <th className="text-left p-3 text-xs font-semibold text-[#334155]">Line</th>
                          <th className="text-left p-3 text-xs font-semibold text-[#334155]">Item</th>
                          <th className="text-left p-3 text-xs font-semibold text-[#334155]">Lab</th>
                          <th className="text-left p-3 text-xs font-semibold text-[#334155]">Category</th>
                          <th className="text-left p-3 text-xs font-semibold text-[#334155]">PR Date</th>
                          <th className="text-right p-3 text-xs font-semibold text-[#334155]">Qty</th>
                          <th className="text-right p-3 text-xs font-semibold text-[#334155]">Unit Rate</th>
                          <th className="text-right p-3 text-xs font-semibold text-[#334155]">Amount + GST</th>
                          <th className="text-left p-3 text-xs font-semibold text-[#334155]">Status</th>
                        </tr>
                      </thead>
                      <tbody>
                        {pr.lines.map((line) => (
                          <Fragment key={line.pr_line_id}>
                            <tr className="border-b border-[#e2e8f0] last:border-0 even:bg-[#f1f5f9] hover:bg-[#e0f2fe]">
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
        recordCount={filteredRecords.length}
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
