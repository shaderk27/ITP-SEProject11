import { Fragment, useEffect, useState } from "react";
import { Link } from "react-router";
import { CheckCircle, ChevronDown, ChevronRight, Eye, Lock, RefreshCw, Upload } from "lucide-react";
import { Card } from "../components/ui/card";
import { FilterBar } from "../components/shared/FilterBar";
import { StatusBadge } from "../components/shared/StatusBadge";
import { Button } from "../components/ui/button";
import { useAuth } from "../context/AuthContext";
import { commitBatch, getBatchDetail, listReviewBatches } from "../services/reviewService";
import type {
  ReviewBatchDetail,
  ReviewBatchSummary,
  ReviewPRGroup,
  ReviewQueueLine,
} from "../types/review";

type DetailState =
  | { kind: "loading" }
  | { kind: "ready"; data: ReviewBatchDetail }
  | { kind: "error"; message: string };

export function ReviewQueuePage() {
  const { user } = useAuth();

  const [batches, setBatches] = useState<ReviewBatchSummary[]>([]);
  const [expandedBatch, setExpandedBatch] = useState<number | null>(null);
  const [expandedPr, setExpandedPr] = useState<string | null>(null);
  const [details, setDetails] = useState<Record<number, DetailState>>({});
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [committingBatch, setCommittingBatch] = useState<number | null>(null);
  const [commitSuccess, setCommitSuccess] = useState<string | null>(null);

  const fetchBatches = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listReviewBatches();
      setBatches(data);
      // Reset detail cache when batch list refreshes; otherwise stale data lingers.
      setDetails({});
      if (data.length > 0) {
        setExpandedBatch(data[0].batch_id);
      } else {
        setExpandedBatch(null);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load review queue.");
      setBatches([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    // eslint-disable-next-line react-hooks/set-state-in-effect
    fetchBatches();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.email]);

  // Lazy-fetch per-batch detail when expanded for the first time.
  useEffect(() => {
    if (expandedBatch === null) return;
    if (details[expandedBatch]) return;
    // eslint-disable-next-line react-hooks/set-state-in-effect
    setDetails((prev) => ({ ...prev, [expandedBatch]: { kind: "loading" } }));
    getBatchDetail(expandedBatch)
      .then((data) => {
        setDetails((prev) => ({ ...prev, [expandedBatch]: { kind: "ready", data } }));
        // Auto-expand the first PR for convenience.
        if (data.prs.length > 0) {
          setExpandedPr(data.prs[0].source_pr_number);
        }
      })
      .catch((err) =>
        setDetails((prev) => ({
          ...prev,
          [expandedBatch]: {
            kind: "error",
            message: err instanceof Error ? err.message : "Failed to load batch detail.",
          },
        })),
      );
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [expandedBatch]);

  const totalOpen = batches.reduce((sum, b) => sum + b.open_queue_count, 0);

  const handleCommit = async (batch: ReviewBatchSummary) => {
    const ok = window.confirm(
      `Commit batch #${batch.batch_id} (${batch.filename})?\n\n` +
        `This will move ${batch.total_lines} reviewed line${batch.total_lines === 1 ? "" : "s"} ` +
        `from staging into the finalized purchase records. This cannot be undone.`,
    );
    if (!ok) return;
    setCommittingBatch(batch.batch_id);
    setCommitSuccess(null);
    try {
      const result = await commitBatch(batch.batch_id);
      const parts: string[] = [];
      if (result.prs_created > 0) {
        parts.push(`${result.prs_created} new PR${result.prs_created === 1 ? "" : "s"}`);
      }
      if (result.prs_updated > 0) {
        parts.push(`${result.prs_updated} updated PR${result.prs_updated === 1 ? "" : "s"}`);
      }
      const prSummary = parts.length > 0 ? parts.join(" + ") : "0 PRs";
      setCommitSuccess(
        `Batch #${result.batch_id} committed: ${prSummary}` +
          ` and ${result.lines_created} line${result.lines_created === 1 ? "" : "s"} written to final tables.`,
      );
      await fetchBatches();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to commit batch.");
    } finally {
      setCommittingBatch(null);
    }
  };

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa]">
      <FilterBar
        searchPlaceholder="Search batch, PR, line item, WBS, requestor..."
        filters={[
          {
            label: "Upload Batch",
            options: [
              { value: "all", label: "All Batches" },
              ...batches.map((b) => ({ value: String(b.batch_id), label: b.filename })),
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
        <div className="mb-6 flex items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold text-foreground">Review Queue</h2>
            <p className="text-sm text-muted-foreground mt-1">
              {loading
                ? "Loading…"
                : `${totalOpen} unresolved line error${totalOpen === 1 ? "" : "s"} across ${batches.length} upload batch${batches.length === 1 ? "" : "es"}.`}
            </p>
          </div>
          <Button size="sm" variant="outline" onClick={fetchBatches} disabled={loading}>
            <RefreshCw className={`h-4 w-4 mr-1 ${loading ? "animate-spin" : ""}`} />
            Refresh
          </Button>
        </div>

        <Card className="p-4 bg-[#fff7ed] border-[#fed7aa] mb-6">
          <div className="flex items-start gap-3">
            <Lock className="h-5 w-5 text-[#c2410c] mt-0.5" />
            <div>
              <p className="text-sm font-medium text-[#9a3412]">
                Expand a batch, then expand a PR to see its individual error lines.
              </p>
              <p className="text-sm text-[#9a3412] mt-1">
                A batch can only be committed after every listed line error in that batch is resolved.
              </p>
            </div>
          </div>
        </Card>

        {error && (
          <Card className="p-4 mb-4 bg-[#fef2f2] border-[#fecaca]">
            <p className="text-sm text-[#b91c1c]">{error}</p>
          </Card>
        )}

        {commitSuccess && (
          <Card className="p-4 mb-4 bg-[#f0fdf4] border-[#bbf7d0]">
            <div className="flex items-start gap-3">
              <CheckCircle className="h-5 w-5 text-[#15803d] mt-0.5" />
              <p className="text-sm text-[#14532d]">{commitSuccess}</p>
            </div>
          </Card>
        )}

        {!loading && !error && batches.length === 0 && (
          <Card className="p-8 text-center text-muted-foreground">
            <p className="text-sm">No upload batches need review right now. Upload a file to get started.</p>
          </Card>
        )}

        <div className="space-y-4">
          {batches.map((batch) => {
            const isBatchExpanded = expandedBatch === batch.batch_id;
            const detail = details[batch.batch_id];
            const canCommit = batch.upload_status === "ready_to_commit" && batch.open_queue_count === 0;
            const isCommittingThis = committingBatch === batch.batch_id;

            return (
              <Card key={batch.batch_id} className="bg-white border-[#cbd5e1] overflow-hidden">
                <div
                  className={`w-full p-5 flex items-center justify-between gap-4 ${
                    isBatchExpanded ? "bg-[#e2e8f0]" : "hover:bg-[#f1f5f9]"
                  }`}
                >
                  <button
                    type="button"
                    className="flex items-center gap-3 text-left flex-1"
                    onClick={() => setExpandedBatch(isBatchExpanded ? null : batch.batch_id)}
                  >
                    {isBatchExpanded ? <ChevronDown className="h-5 w-5" /> : <ChevronRight className="h-5 w-5" />}
                    <div>
                      <p className="text-lg font-semibold text-foreground">
                        Batch #{batch.batch_id} — {batch.filename}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        {batch.open_queue_count} unresolved / {batch.total_lines} total lines · Uploaded by{" "}
                        {batch.uploader_name} · {formatDate(batch.uploaded_at)}
                      </p>
                    </div>
                  </button>
                  <div className="flex items-center gap-3">
                    <StatusBadge status="pending">{prettyStatus(batch.upload_status)}</StatusBadge>
                    {canCommit && (
                      <Button
                        size="sm"
                        onClick={(e) => {
                          e.stopPropagation();
                          handleCommit(batch);
                        }}
                        disabled={isCommittingThis}
                        className="bg-[#15803d] hover:bg-[#166534] text-white"
                      >
                        <Upload className="h-4 w-4 mr-1" />
                        {isCommittingThis ? "Committing…" : "Commit Batch"}
                      </Button>
                    )}
                  </div>
                </div>

                {isBatchExpanded && (
                  <div className="border-t border-[#cbd5e1] bg-[#f1f5f9] p-4 space-y-3">
                    {!detail || detail.kind === "loading" ? (
                      <p className="text-sm text-muted-foreground py-2 px-1">Loading line errors…</p>
                    ) : detail.kind === "error" ? (
                      <p className="text-sm text-[#b91c1c] py-2 px-1">{detail.message}</p>
                    ) : detail.data.prs.length === 0 ? (
                      <p className="text-sm text-muted-foreground py-2 px-1">
                        No line errors visible to you in this batch.
                      </p>
                    ) : (
                      detail.data.prs.map((pr) => (
                        <PRGroupCard
                          key={pr.source_pr_number}
                          pr={pr}
                          isExpanded={expandedPr === pr.source_pr_number}
                          onToggle={() =>
                            setExpandedPr(expandedPr === pr.source_pr_number ? null : pr.source_pr_number)
                          }
                        />
                      ))
                    )}
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

// ─── PR-level row ────────────────────────────────────────────────────────
function PRGroupCard({
  pr,
  isExpanded,
  onToggle,
}: {
  pr: ReviewPRGroup;
  isExpanded: boolean;
  onToggle: () => void;
}) {
  const total = pr.lines.length;
  const openCount = pr.lines.filter((l) => l.queue_status === "open").length;
  const allResolved = openCount === 0;
  return (
    <div
      className={`rounded-md border border-[#cbd5e1] border-l-4 bg-white overflow-hidden ${
        allResolved ? "border-l-[#10b981]" : "border-l-[#f59e0b]"
      }`}
    >
      <button
        type="button"
        className={`w-full p-4 flex items-center justify-between gap-4 text-left ${
          isExpanded ? "bg-[#f8fafc]" : "hover:bg-[#f8fafc]"
        }`}
        onClick={onToggle}
      >
        <div className="flex items-center gap-3">
          {isExpanded ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}
          <div>
            <p className="text-sm font-semibold text-foreground">{pr.source_pr_number}</p>
            <p className="text-xs text-muted-foreground">
              {allResolved
                ? `${total} line${total === 1 ? "" : "s"} · all resolved`
                : `${openCount} unresolved of ${total} line${total === 1 ? "" : "s"}`}
              {pr.requestor_name ? ` · ${pr.requestor_name}` : ""}
            </p>
          </div>
        </div>
        {allResolved ? (
          <StatusBadge status="healthy">Resolved</StatusBadge>
        ) : (
          <StatusBadge status="warning">Needs line edits</StatusBadge>
        )}
      </button>

      {isExpanded && (
        <div className="border-t border-[#cbd5e1] overflow-x-auto">
          <table className="w-full">
            <thead className="bg-[#e2e8f0]">
              <tr className="border-b border-[#cbd5e1]">
                <th className="text-left p-3 text-xs font-semibold text-[#334155]">Line</th>
                <th className="text-left p-3 text-xs font-semibold text-[#334155]">Item</th>
                <th className="text-left p-3 text-xs font-semibold text-[#334155]">WBS</th>
                <th className="text-left p-3 text-xs font-semibold text-[#334155]">Current Classification</th>
                <th className="text-left p-3 text-xs font-semibold text-[#334155]">Issue</th>
                <th className="text-right p-3 text-xs font-semibold text-[#334155]">Amount + GST</th>
                <th className="text-center p-3 text-xs font-semibold text-[#334155]">Status</th>
                <th className="text-center p-3 text-xs font-semibold text-[#334155]">Action</th>
              </tr>
            </thead>
            <tbody>
              {pr.lines.map((line) => (
                <LineRow key={line.review_queue_id} line={line} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

// ─── Line-level row ──────────────────────────────────────────────────────
function LineRow({ line }: { line: ReviewQueueLine }) {
  return (
    <Fragment>
      <tr className="border-b border-[#e2e8f0] last:border-0 even:bg-[#f1f5f9] hover:bg-[#e0f2fe]">
        <td className="p-3 text-sm font-medium text-foreground">
          Line {line.source_line_no ?? "—"}
        </td>
        <td className="p-3 text-sm text-foreground">{line.item_details}</td>
        <td className="p-3 text-sm text-muted-foreground">{line.wbs_code || "—"}</td>
        <td className="p-3">
          <div className="flex flex-wrap gap-2">
            <StatusBadge status={line.is_lab_group_general ? "general" : "info"}>
              {line.current_lab_group}
            </StatusBadge>
            <StatusBadge status={line.is_lab_general ? "general" : "info"}>
              {line.current_lab}
            </StatusBadge>
            <StatusBadge status={line.is_category_general ? "general" : "info"}>
              {line.current_category}
            </StatusBadge>
          </div>
        </td>
        <td className="p-3 text-xs text-muted-foreground max-w-sm">{line.review_reason}</td>
        <td className="p-3 text-sm text-right font-medium text-foreground">
          ${formatAmount(line.amount_gst)}
        </td>
        <td className="p-3 text-center">
          {line.queue_status === "resolved" ? (
            <StatusBadge status="healthy">Resolved</StatusBadge>
          ) : (
            <StatusBadge status="warning">Open</StatusBadge>
          )}
        </td>
        <td className="p-3 text-center">
          <Link to={`/review/${line.review_queue_id}`}>
            <Button size="sm" variant="outline">
              <Eye className="h-4 w-4 mr-1" />
              Edit Line
            </Button>
          </Link>
        </td>
      </tr>
    </Fragment>
  );
}

// ─── Tiny helpers ────────────────────────────────────────────────────────
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

function prettyStatus(raw: string): string {
  return raw.replace(/_/g, " ").replace(/\b\w/g, (c) => c.toUpperCase());
}

function formatAmount(raw: string): string {
  const num = Number(raw);
  if (Number.isNaN(num)) return raw;
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
