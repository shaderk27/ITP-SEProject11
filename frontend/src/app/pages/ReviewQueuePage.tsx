import { useEffect, useState } from "react";
import { ChevronDown, ChevronRight, Lock, RefreshCw } from "lucide-react";
import { Card } from "../components/ui/card";
import { FilterBar } from "../components/shared/FilterBar";
import { StatusBadge } from "../components/shared/StatusBadge";
import { Button } from "../components/ui/button";
import { useAuth } from "../context/AuthContext";
import { listReviewBatches } from "../services/reviewService";
import type { ReviewBatchSummary } from "../types/review";

export function ReviewQueuePage() {
  const { user } = useAuth();
  const [batches, setBatches] = useState<ReviewBatchSummary[]>([]);
  const [expandedBatch, setExpandedBatch] = useState<number | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const fetchBatches = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await listReviewBatches(user);
      setBatches(data);
      if (data.length > 0 && expandedBatch === null) {
        setExpandedBatch(data[0].batch_id);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Failed to load review queue.");
      setBatches([]);
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchBatches();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [user?.email]);

  const totalOpen = batches.reduce((sum, b) => sum + b.open_queue_count, 0);

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
                Expand a batch to see its review summary.
              </p>
              <p className="text-sm text-[#9a3412] mt-1">
                Per-line correction UI ships in the next step. A batch can only be committed after every listed line error in that batch is resolved.
              </p>
            </div>
          </div>
        </Card>

        {error && (
          <Card className="p-4 mb-4 bg-[#fef2f2] border-[#fecaca]">
            <p className="text-sm text-[#b91c1c]">{error}</p>
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
            return (
              <Card key={batch.batch_id} className="bg-white border-border overflow-hidden">
                <button
                  type="button"
                  className="w-full p-5 flex items-center justify-between gap-4 text-left hover:bg-[#f8f9fa]"
                  onClick={() => setExpandedBatch(isBatchExpanded ? null : batch.batch_id)}
                >
                  <div className="flex items-center gap-3">
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
                  </div>
                  <StatusBadge status="pending">{prettyStatus(batch.upload_status)}</StatusBadge>
                </button>

                {isBatchExpanded && (
                  <div className="border-t border-border bg-[#f8f9fa] p-6">
                    <p className="text-sm text-muted-foreground">
                      <strong className="text-foreground">{batch.open_queue_count}</strong> line error
                      {batch.open_queue_count === 1 ? "" : "s"} in this batch are waiting for review. The
                      per-line correction interface will appear here in the next step.
                    </p>
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
