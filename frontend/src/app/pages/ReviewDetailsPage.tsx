import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router";
import { AlertCircle, ArrowLeft, CheckCircle, Info } from "lucide-react";
import { Card } from "../components/ui/card";
import { Button } from "../components/ui/button";
import { Label } from "../components/ui/label";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "../components/ui/select";
import { Textarea } from "../components/ui/textarea";
import { StatusBadge } from "../components/shared/StatusBadge";
import { useAuth } from "../context/AuthContext";
import { getQueueItem, saveCorrection } from "../services/reviewService";
import type { QueueItemDetail } from "../types/review";

export function ReviewDetailsPage() {
  const navigate = useNavigate();
  const { user } = useAuth();
  const { id } = useParams<{ id: string }>();
  const queueId = Number(id);

  const [item, setItem] = useState<QueueItemDetail | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);

  // Form state — initialized from server's suggestions once loaded.
  const [labGroupId, setLabGroupId] = useState<number | null>(null);
  const [labId, setLabId] = useState<number | null>(null);
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [comment, setComment] = useState("");

  useEffect(() => {
    if (!Number.isFinite(queueId)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setError(`Invalid review queue id: ${id}`);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    getQueueItem(queueId, user)
      .then((data) => {
        setItem(data);
        setLabGroupId(data.suggested_lab_group_id);
        setLabId(data.suggested_lab_id);
        setCategoryId(data.suggested_category_id);
      })
      .catch((err) => setError(err instanceof Error ? err.message : "Failed to load queue item."))
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queueId, user?.email]);

  // Labs filtered by selected lab group — cascading dropdown.
  const labsForGroup = useMemo(() => {
    if (!item || labGroupId === null) return [];
    return item.available_labs.filter((l) => l.lab_group_id === labGroupId);
  }, [item, labGroupId]);

  // If user picks a new Lab Group whose labs don't include the current Lab, reset Lab.
  useEffect(() => {
    if (!item || labGroupId === null || labId === null) return;
    const stillValid = labsForGroup.some((l) => l.lab_id === labId);
    if (!stillValid) {
      // Default to the General lab in this group, if one exists.
      const general = labsForGroup.find((l) => l.is_general);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLabId(general?.lab_id ?? labsForGroup[0]?.lab_id ?? null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [labGroupId]);

  // Edits are allowed until the batch is committed. Inside a not-yet-committed
  // batch, Team Leads can re-correct a saved line as many times as needed.
  const isLocked = !!item && item.batch_upload_status === "committed";
  const canSave =
    !!item &&
    !saving &&
    !isLocked &&
    labGroupId !== null &&
    labId !== null &&
    categoryId !== null;

  const handleSave = async () => {
    if (!canSave || labGroupId === null || labId === null || categoryId === null) return;
    setSaving(true);
    setSaveError(null);
    try {
      const result = await saveCorrection(
        queueId,
        {
          lab_group_id: labGroupId,
          lab_id: labId,
          category_id: categoryId,
          comment: comment.trim() || undefined,
        },
        user,
      );
      // On success, head back to the queue with a friendly toast-like signal.
      navigate(`/review?resolved=${result.review_queue_id}`);
    } catch (err) {
      setSaveError(err instanceof Error ? err.message : "Failed to save correction.");
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa]">
      <div className="p-6 space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold text-foreground">Resolve Review Line</h2>
            {item && (
              <p className="text-sm text-muted-foreground mt-1">
                {item.source_pr_number} · Line {item.source_line_no ?? "—"} · from{" "}
                <span className="font-medium">{item.batch_filename}</span> (batch #{item.batch_id})
              </p>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              Saving this page resolves only this line. The upload batch can be committed once every line in it is resolved.
            </p>
          </div>
          <Button variant="outline" size="sm" onClick={() => navigate("/review")}>
            <ArrowLeft className="h-4 w-4 mr-1" />
            Back to Queue
          </Button>
        </div>

        {loading && (
          <Card className="p-8 text-center text-muted-foreground">
            <p className="text-sm">Loading queue item…</p>
          </Card>
        )}

        {error && (
          <Card className="p-4 bg-[#fef2f2] border-[#fecaca]">
            <p className="text-sm text-[#b91c1c]">{error}</p>
          </Card>
        )}

        {item && isLocked && (
          <Card className="p-4 bg-[#f0fdf4] border-[#bbf7d0]">
            <div className="flex items-start gap-3">
              <CheckCircle className="h-5 w-5 text-[#15803d] mt-0.5" />
              <div>
                <p className="text-sm font-medium text-[#14532d]">
                  Batch #{item.batch_id} has been committed. This line is locked.
                </p>
                <p className="text-sm text-[#14532d] mt-1">
                  No further edits are accepted. Use Back to Queue to pick another line.
                </p>
              </div>
            </div>
          </Card>
        )}

        {item && !isLocked && item.queue_status === "resolved" && (
          <Card className="p-4 bg-[#fff7ed] border-[#fed7aa]">
            <div className="flex items-start gap-3">
              <CheckCircle className="h-5 w-5 text-[#c2410c] mt-0.5" />
              <div>
                <p className="text-sm font-medium text-[#9a3412]">
                  This line was already saved — you can still edit it until the batch is committed.
                </p>
                {item.last_action && (
                  <p className="text-sm text-[#9a3412] mt-1">
                    Last corrected by <strong>{item.last_action.reviewer_name}</strong> at{" "}
                    {formatDate(item.last_action.reviewed_at)}
                    {item.last_action.comment ? ` · "${item.last_action.comment}"` : ""}.
                  </p>
                )}
              </div>
            </div>
          </Card>
        )}

        {item && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left: read-only context */}
            <div className="lg:col-span-2 space-y-6">
              <Card className="p-6">
                <h3 className="text-lg font-semibold flex items-center gap-2 mb-4">
                  <Info className="h-5 w-5 text-[#2563eb]" />
                  Uploaded Line Data
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                  <Field label="Item Details" value={item.item_details} />
                  <Field label="Purpose" value={item.purpose} />
                  <Field label="Instruction to Vendor" value={item.instruction_to_vendor} />
                  <Field label="WBS" value={item.wbs_code} />
                  <Field label="Requestor" value={item.requestor_name} />
                  <Field label="Amount + GST" value={`$${formatAmount(item.amount_gst)}`} />
                  <Field label="Qty" value={item.qty ?? "—"} />
                  <Field label="Unit Rate" value={item.unit_rate ? `$${formatAmount(item.unit_rate)}` : "—"} />
                  <Field label="PR Submitted" value={item.pr_sub_date ?? "—"} />
                </div>
              </Card>

              <Card className="p-6">
                <h3 className="text-lg font-semibold flex items-center gap-2 mb-3">
                  <AlertCircle className="h-5 w-5 text-[#c2410c]" />
                  Review Reason
                </h3>
                <p className="text-sm text-foreground whitespace-pre-line">
                  {item.review_reason || "No reason provided by the classifier."}
                </p>
                <div className="mt-4 flex flex-wrap gap-2 text-xs">
                  <span className="text-muted-foreground">Current:</span>
                  <StatusBadge status={item.is_lab_group_general ? "general" : "info"}>
                    Lab Group: {item.current_lab_group}
                  </StatusBadge>
                  <StatusBadge status={item.is_lab_general ? "general" : "info"}>
                    Lab: {item.current_lab}
                  </StatusBadge>
                  <StatusBadge status={item.is_category_general ? "general" : "info"}>
                    Category: {item.current_category}
                  </StatusBadge>
                </div>
              </Card>
            </div>

            {/* Right: form */}
            <Card className="p-6 space-y-4 self-start">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <CheckCircle className="h-5 w-5 text-[#15803d]" />
                Final Classification
              </h3>

              <div className="space-y-2">
                <Label>Lab Group</Label>
                <Select
                  value={labGroupId !== null ? String(labGroupId) : undefined}
                  onValueChange={(v) => setLabGroupId(Number(v))}
                  disabled={isLocked}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Pick a lab group" />
                  </SelectTrigger>
                  <SelectContent>
                    {item.available_lab_groups.map((g) => (
                      <SelectItem key={g.lab_group_id} value={String(g.lab_group_id)}>
                        {g.lab_group_name}
                        {g.wbs_code ? ` (${g.wbs_code})` : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Lab</Label>
                <Select
                  value={labId !== null ? String(labId) : undefined}
                  onValueChange={(v) => setLabId(Number(v))}
                  disabled={isLocked || labGroupId === null}
                >
                  <SelectTrigger>
                    <SelectValue
                      placeholder={labGroupId === null ? "Pick a lab group first" : "Pick a lab"}
                    />
                  </SelectTrigger>
                  <SelectContent>
                    {labsForGroup.map((l) => (
                      <SelectItem key={l.lab_id} value={String(l.lab_id)}>
                        {l.lab_name}
                        {l.is_general ? " (general)" : ""}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Category</Label>
                <Select
                  value={categoryId !== null ? String(categoryId) : undefined}
                  onValueChange={(v) => setCategoryId(Number(v))}
                  disabled={isLocked}
                >
                  <SelectTrigger>
                    <SelectValue placeholder="Pick a category" />
                  </SelectTrigger>
                  <SelectContent>
                    {item.available_categories.map((c) => (
                      <SelectItem key={c.category_id} value={String(c.category_id)}>
                        {c.category_name}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Audit Note (optional)</Label>
                <Textarea
                  placeholder="Reason for manual correction…"
                  value={comment}
                  onChange={(e) => setComment(e.target.value)}
                  disabled={isLocked}
                />
              </div>

              {saveError && (
                <div className="p-3 rounded-md bg-[#fef2f2] border border-[#fecaca]">
                  <p className="text-sm text-[#b91c1c]">{saveError}</p>
                </div>
              )}

              <div className="flex gap-2 pt-2">
                <Button variant="outline" className="flex-1" onClick={() => navigate("/review")}>
                  Cancel
                </Button>
                <Button className="flex-1" onClick={handleSave} disabled={!canSave}>
                  {saving ? "Saving…" : "Save Correction"}
                </Button>
              </div>
            </Card>
          </div>
        )}
      </div>
    </div>
  );
}

function Field({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-sm text-foreground mt-1 whitespace-pre-line">{value || "—"}</p>
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

function formatAmount(raw: string): string {
  const num = Number(raw);
  if (Number.isNaN(num)) return raw;
  return num.toLocaleString(undefined, { minimumFractionDigits: 2, maximumFractionDigits: 2 });
}
