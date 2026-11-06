import { useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router";
import {
  AlertCircle,
  ArrowLeft,
  CheckCircle,
  GitBranch,
  Info,
  Plus,
  Trash2,
} from "lucide-react";
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

interface EditableAllocationRow {
  wbs_code: string;
  amount_gst: string;
  lab_group_id: number | null;
  lab_id: number | null;
  category_id: number | null;
}

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

  // Single-line form state
  const [labGroupId, setLabGroupId] = useState<number | null>(null);
  const [labId, setLabId] = useState<number | null>(null);
  const [categoryId, setCategoryId] = useState<number | null>(null);
  const [comment, setComment] = useState("");

  // Multi-WBS allocations form state
  const [allocRows, setAllocRows] = useState<EditableAllocationRow[]>([]);

  useEffect(() => {
    if (!Number.isFinite(queueId)) {
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setError(`Invalid review queue id: ${id}`);
      setLoading(false);
      return;
    }
    setLoading(true);
    setError(null);
    getQueueItem(queueId)
      .then((data) => {
        setItem(data);
        setLabGroupId(data.suggested_lab_group_id);
        setLabId(data.suggested_lab_id);
        setCategoryId(data.suggested_category_id);

        if (data.wbs_allocations && data.wbs_allocations.length > 1) {
          setAllocRows(
            data.wbs_allocations.map((a) => ({
              wbs_code: a.wbs_code || "",
              amount_gst: a.amount_gst ?? "",
              lab_group_id:
                a.suggested_lab_group_id ?? data.suggested_lab_group_id,
              lab_id: a.suggested_lab_id ?? data.suggested_lab_id,
              category_id:
                a.suggested_category_id ?? data.suggested_category_id,
            })),
          );
        } else {
          setAllocRows([]);
        }
      })
      .catch((err) =>
        setError(
          err instanceof Error ? err.message : "Failed to load queue item.",
        ),
      )
      .finally(() => setLoading(false));
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [queueId, user?.email]);

  // Labs filtered by selected lab group — cascading dropdown for single-WBS mode.
  const labsForGroup = useMemo(() => {
    if (!item || labGroupId === null) return [];
    return item.available_labs.filter((l) => l.lab_group_id === labGroupId);
  }, [item, labGroupId]);

  // If user picks a new Lab Group whose labs don't include the current Lab, reset Lab.
  useEffect(() => {
    if (!item || labGroupId === null || labId === null) return;
    const stillValid = labsForGroup.some((l) => l.lab_id === labId);
    if (!stillValid) {
      const general = labsForGroup.find((l) => l.is_general);
      // eslint-disable-next-line react-hooks/set-state-in-effect
      setLabId(general?.lab_id ?? labsForGroup[0]?.lab_id ?? null);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [labGroupId]);

  const isMultiWbs = allocRows.length > 1;
  const isLocked = !!item && item.batch_upload_status === "committed";

  const lineTargetAmount = Number(item?.amount_gst ?? 0);
  const currentAllocatedSum = allocRows.reduce((sum, row) => {
    const val = parseFloat(row.amount_gst);
    return sum + (Number.isFinite(val) ? val : 0);
  }, 0);
  const allocationDiff = Number(
    (lineTargetAmount - currentAllocatedSum).toFixed(2),
  );
  const isAllocationSumReconciled = Math.abs(allocationDiff) <= 0.01;

  const areAllAllocRowsComplete =
    isMultiWbs &&
    allocRows.every((row) => {
      const amt = parseFloat(row.amount_gst);
      return (
        row.wbs_code.trim().length > 0 &&
        Number.isFinite(amt) &&
        amt > 0 &&
        row.lab_group_id !== null &&
        row.lab_id !== null &&
        row.category_id !== null
      );
    });

  const canSave =
    !!item &&
    !saving &&
    !isLocked &&
    (isMultiWbs
      ? areAllAllocRowsComplete && isAllocationSumReconciled
      : labGroupId !== null && labId !== null && categoryId !== null);

  const updateAllocRow = (
    index: number,
    patch: Partial<EditableAllocationRow>,
  ) => {
    if (!item) return;
    setAllocRows((prev) =>
      prev.map((row, idx) => {
        if (idx !== index) return row;
        const updated = { ...row, ...patch };
        if (
          patch.lab_group_id !== undefined &&
          patch.lab_group_id !== row.lab_group_id
        ) {
          const groupLabs = item.available_labs.filter(
            (l) => l.lab_group_id === patch.lab_group_id,
          );
          const stillValid = groupLabs.some((l) => l.lab_id === updated.lab_id);
          if (!stillValid) {
            const general = groupLabs.find((l) => l.is_general);
            updated.lab_id = general?.lab_id ?? groupLabs[0]?.lab_id ?? null;
          }
        }
        return updated;
      }),
    );
  };

  const handleAddAllocRow = () => {
    if (!item) return;
    const defaultGroupId =
      allocRows[0]?.lab_group_id ??
      item.suggested_lab_group_id ??
      item.available_lab_groups[0]?.lab_group_id ??
      null;
    const groupLabs = item.available_labs.filter(
      (l) => l.lab_group_id === defaultGroupId,
    );
    const defaultLabId =
      groupLabs.find((l) => l.is_general)?.lab_id ??
      groupLabs[0]?.lab_id ??
      null;
    const defaultCatId =
      allocRows[0]?.category_id ??
      item.suggested_category_id ??
      item.available_categories[0]?.category_id ??
      null;

    setAllocRows((prev) => [
      ...prev,
      {
        wbs_code: "",
        amount_gst: allocationDiff > 0 ? allocationDiff.toFixed(2) : "0.00",
        lab_group_id: defaultGroupId,
        lab_id: defaultLabId,
        category_id: defaultCatId,
      },
    ]);
  };

  const handleRemoveAllocRow = (index: number) => {
    if (allocRows.length <= 2) return;
    setAllocRows((prev) => prev.filter((_, idx) => idx !== index));
  };

  const handleSave = async () => {
    if (!canSave) return;
    setSaving(true);
    setSaveError(null);
    try {
      const payload = isMultiWbs
        ? {
            comment: comment.trim() || undefined,
            allocations: allocRows.map((row) => ({
              wbs_code: row.wbs_code.trim(),
              amount_gst: Number(parseFloat(row.amount_gst).toFixed(2)),
              lab_group_id: row.lab_group_id as number,
              lab_id: row.lab_id as number,
              category_id: row.category_id as number,
            })),
          }
        : {
            lab_group_id: labGroupId as number,
            lab_id: labId as number,
            category_id: categoryId as number,
            comment: comment.trim() || undefined,
          };

      const result = await saveCorrection(queueId, payload);
      navigate(`/review?resolved=${result.review_queue_id}`);
    } catch (err) {
      setSaveError(
        err instanceof Error ? err.message : "Failed to save correction.",
      );
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="h-full overflow-auto bg-[#f8f9fa]">
      <div className="p-6 space-y-6">
        <div className="flex items-start justify-between gap-4">
          <div>
            <h2 className="text-2xl font-semibold text-foreground">
              Resolve Review Line
            </h2>
            {item && (
              <p className="text-sm text-muted-foreground mt-1">
                {item.source_pr_number} · Line {item.source_line_no ?? "—"} ·
                from <span className="font-medium">{item.batch_filename}</span>{" "}
                (batch #{item.batch_id})
              </p>
            )}
            <p className="text-xs text-muted-foreground mt-1">
              Saving this page resolves only this line. The upload batch can be
              committed once every line in it is resolved.
            </p>
          </div>
          <Button
            variant="outline"
            size="sm"
            onClick={() => navigate("/review")}
          >
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
                  Batch #{item.batch_id} has been committed. This line is
                  locked.
                </p>
                <p className="text-sm text-[#14532d] mt-1">
                  No further edits are accepted. Use Back to Queue to pick
                  another line.
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
                  This line was already saved — you can still edit it until the
                  batch is committed.
                </p>
                {item.last_action && (
                  <p className="text-sm text-[#9a3412] mt-1">
                    Last corrected by{" "}
                    <strong>{item.last_action.reviewer_name}</strong> at{" "}
                    {formatDate(item.last_action.reviewed_at)}
                    {item.last_action.comment
                      ? ` · "${item.last_action.comment}"`
                      : ""}
                    .
                  </p>
                )}
              </div>
            </div>
          </Card>
        )}

        {item && (
          <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
            {/* Left: read-only context + Multi-WBS editor when applicable */}
            <div className="lg:col-span-2 space-y-6">
              <Card className="p-6">
                <h3 className="text-lg font-semibold flex items-center gap-2 mb-4">
                  <Info className="h-5 w-5 text-[#2563eb]" />
                  Uploaded Line Data
                </h3>
                <div className="grid grid-cols-2 md:grid-cols-3 gap-4 text-sm">
                  <Field label="Item Details" value={item.item_details} />
                  <Field label="Purpose" value={item.purpose} />
                  <Field
                    label="Instruction to Vendor"
                    value={item.instruction_to_vendor}
                  />
                  <Field label="WBS" value={item.wbs_code} />
                  <Field label="Requestor" value={item.requestor_name} />
                  <Field
                    label="Original Line Amount + GST"
                    value={`$${formatAmount(item.amount_gst)}`}
                  />
                  <Field label="Qty" value={item.qty ?? "—"} />
                  <Field
                    label="Unit Rate"
                    value={
                      item.unit_rate ? `$${formatAmount(item.unit_rate)}` : "—"
                    }
                  />
                  <Field label="PR Submitted" value={item.pr_sub_date ?? "—"} />
                </div>
              </Card>

              <Card className="p-6">
                <h3 className="text-lg font-semibold flex items-center gap-2 mb-3">
                  <AlertCircle className="h-5 w-5 text-[#c2410c]" />
                  Review Reason
                </h3>
                <p className="text-sm text-foreground whitespace-pre-line">
                  {item.review_reason ||
                    "No reason provided by the classifier."}
                </p>
                {!isMultiWbs && (
                  <div className="mt-4 flex flex-wrap gap-2 text-xs">
                    <span className="text-muted-foreground">Current:</span>
                    <StatusBadge
                      status={item.is_lab_group_general ? "general" : "info"}
                    >
                      Lab Group: {item.current_lab_group}
                    </StatusBadge>
                    <StatusBadge
                      status={item.is_lab_general ? "general" : "info"}
                    >
                      Lab: {item.current_lab}
                    </StatusBadge>
                    <StatusBadge
                      status={item.is_category_general ? "general" : "info"}
                    >
                      Category: {item.current_category}
                    </StatusBadge>
                  </div>
                )}
              </Card>

              {isMultiWbs && (
                <Card className="p-6 space-y-4">
                  <div className="flex flex-wrap items-center justify-between gap-3">
                    <div>
                      <h3 className="text-lg font-semibold flex items-center gap-2 text-[#1e3a8a]">
                        <GitBranch className="h-5 w-5" />
                        WBS Transaction Allocations
                      </h3>
                      <p className="text-xs text-muted-foreground mt-0.5">
                        Confirm the Lab Group, Lab, Category, and exact monetary
                        allocation for each WBS portion. Portions must sum
                        exactly to ${formatAmount(item.amount_gst)}.
                      </p>
                    </div>
                    {!isLocked && (
                      <Button
                        type="button"
                        size="sm"
                        variant="outline"
                        onClick={handleAddAllocRow}
                      >
                        <Plus className="h-3.5 w-3.5 mr-1" />
                        Add WBS Portion
                      </Button>
                    )}
                  </div>

                  {/* Reconciliation Banner */}
                  <div
                    className={`rounded-md border p-3 text-xs flex flex-wrap items-center justify-between gap-2 ${
                      isAllocationSumReconciled
                        ? "bg-[#f0fdf4] border-[#bbf7d0] text-[#14532d]"
                        : "bg-[#fef2f2] border-[#fecaca] text-[#b91c1c]"
                    }`}
                  >
                    <div>
                      <span className="font-semibold">
                        Original Purchase Item Amount:
                      </span>{" "}
                      ${formatAmount(item.amount_gst)} ·{" "}
                      <span className="font-semibold">Allocated Sum:</span> $
                      {formatAmount(String(currentAllocatedSum.toFixed(2)))}
                    </div>
                    <div className="font-bold">
                      {isAllocationSumReconciled
                        ? "Reconciled ($0.00 difference)"
                        : `Unreconciled Difference: $${formatAmount(String(Math.abs(allocationDiff).toFixed(2)))} ${
                            allocationDiff > 0 ? "under" : "over"
                          }`}
                    </div>
                  </div>

                  {/* Allocation Portion Cards */}
                  <div className="space-y-3">
                    {allocRows.map((row, idx) => {
                      const rowLabs =
                        row.lab_group_id !== null
                          ? item.available_labs.filter(
                              (l) => l.lab_group_id === row.lab_group_id,
                            )
                          : [];

                      return (
                        <div
                          key={idx}
                          className="rounded-lg border border-[#cbd5e1] bg-[#f8fafc] p-4 space-y-3"
                        >
                          <div className="flex items-center justify-between">
                            <span className="text-xs font-bold uppercase tracking-wider text-[#1e3a8a]">
                              WBS Portion #{idx + 1}
                            </span>
                            {!isLocked && allocRows.length > 2 && (
                              <Button
                                type="button"
                                size="sm"
                                variant="ghost"
                                className="h-7 px-2 text-[#dc2626]"
                                onClick={() => handleRemoveAllocRow(idx)}
                              >
                                <Trash2 className="h-3.5 w-3.5 mr-1" />
                                Remove
                              </Button>
                            )}
                          </div>

                          <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
                            <div>
                              <Label className="text-xs">WBS Code</Label>
                              <input
                                type="text"
                                disabled={isLocked}
                                className="mt-1 w-full rounded-md border border-input bg-white px-3 py-2 text-sm font-mono"
                                placeholder="e.g. R-BCAXX-R203-0004-EQT"
                                value={row.wbs_code}
                                onChange={(e) =>
                                  updateAllocRow(idx, {
                                    wbs_code: e.target.value,
                                  })
                                }
                              />
                            </div>

                            <div>
                              <Label className="text-xs">
                                Allocated Amount + GST (SGD)
                              </Label>
                              <input
                                type="number"
                                step="0.01"
                                min="0.01"
                                disabled={isLocked}
                                className="mt-1 w-full rounded-md border border-input bg-white px-3 py-2 text-sm font-semibold"
                                placeholder="0.00"
                                value={row.amount_gst}
                                onChange={(e) =>
                                  updateAllocRow(idx, {
                                    amount_gst: e.target.value,
                                  })
                                }
                              />
                            </div>

                            <div>
                              <Label className="text-xs">Lab Group</Label>
                              <select
                                disabled={isLocked}
                                className="mt-1 w-full rounded-md border border-input bg-white px-3 py-2 text-sm"
                                value={row.lab_group_id ?? ""}
                                onChange={(e) =>
                                  updateAllocRow(idx, {
                                    lab_group_id: e.target.value
                                      ? Number(e.target.value)
                                      : null,
                                  })
                                }
                              >
                                <option value="" disabled>
                                  Pick a lab group
                                </option>
                                {item.available_lab_groups.map((g) => (
                                  <option
                                    key={g.lab_group_id}
                                    value={g.lab_group_id}
                                  >
                                    {g.lab_group_name}
                                    {g.wbs_code ? ` (${g.wbs_code})` : ""}
                                  </option>
                                ))}
                              </select>
                            </div>

                            <div>
                              <Label className="text-xs">Lab</Label>
                              <select
                                disabled={isLocked || row.lab_group_id === null}
                                className="mt-1 w-full rounded-md border border-input bg-white px-3 py-2 text-sm"
                                value={row.lab_id ?? ""}
                                onChange={(e) =>
                                  updateAllocRow(idx, {
                                    lab_id: e.target.value
                                      ? Number(e.target.value)
                                      : null,
                                  })
                                }
                              >
                                <option value="" disabled>
                                  Pick a lab
                                </option>
                                {rowLabs.map((l) => (
                                  <option key={l.lab_id} value={l.lab_id}>
                                    {l.lab_code
                                      ? `${l.lab_code} ${l.lab_name}`
                                      : l.lab_name}
                                    {l.is_general ? " (general)" : ""}
                                  </option>
                                ))}
                              </select>
                            </div>

                            <div className="md:col-span-2">
                              <Label className="text-xs">
                                Spending Category
                              </Label>
                              <select
                                disabled={isLocked}
                                className="mt-1 w-full rounded-md border border-input bg-white px-3 py-2 text-sm"
                                value={row.category_id ?? ""}
                                onChange={(e) =>
                                  updateAllocRow(idx, {
                                    category_id: e.target.value
                                      ? Number(e.target.value)
                                      : null,
                                  })
                                }
                              >
                                <option value="" disabled>
                                  Pick a category
                                </option>
                                {item.available_categories.map((c) => (
                                  <option
                                    key={c.category_id}
                                    value={c.category_id}
                                  >
                                    {c.category_name}
                                  </option>
                                ))}
                              </select>
                            </div>
                          </div>
                        </div>
                      );
                    })}
                  </div>
                </Card>
              )}
            </div>

            {/* Right: form / confirmation panel */}
            <Card className="p-6 space-y-4 self-start">
              <h3 className="text-lg font-semibold flex items-center gap-2">
                <CheckCircle className="h-5 w-5 text-[#15803d]" />
                {isMultiWbs
                  ? "Confirm Multi-WBS Allocations"
                  : "Final Classification"}
              </h3>

              {!isMultiWbs ? (
                <>
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
                          <SelectItem
                            key={g.lab_group_id}
                            value={String(g.lab_group_id)}
                          >
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
                          placeholder={
                            labGroupId === null
                              ? "Pick a lab group first"
                              : "Pick a lab"
                          }
                        />
                      </SelectTrigger>
                      <SelectContent>
                        {labsForGroup.map((l) => (
                          <SelectItem key={l.lab_id} value={String(l.lab_id)}>
                            {l.lab_code
                              ? `${l.lab_code} ${l.lab_name}`
                              : l.lab_name}
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
                          <SelectItem
                            key={c.category_id}
                            value={String(c.category_id)}
                          >
                            {c.category_name}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                </>
              ) : (
                <div className="rounded-md border border-[#cbd5e1] bg-[#f8fafc] p-3 text-xs space-y-1.5">
                  <p className="font-semibold text-foreground">
                    Allocation Summary ({allocRows.length} portions)
                  </p>
                  {allocRows.map((r, i) => (
                    <div
                      key={i}
                      className="flex items-center justify-between text-muted-foreground"
                    >
                      <span className="font-mono truncate mr-2">
                        {r.wbs_code || `(Portion #${i + 1})`}
                      </span>
                      <span className="font-semibold text-foreground">
                        ${formatAmount(r.amount_gst || "0")}
                      </span>
                    </div>
                  ))}
                  <div className="border-t border-[#cbd5e1] pt-1.5 flex items-center justify-between font-bold text-foreground">
                    <span>Total Allocated</span>
                    <span>
                      ${formatAmount(String(currentAllocatedSum.toFixed(2)))} /
                      ${formatAmount(item.amount_gst)}
                    </span>
                  </div>
                </div>
              )}

              <div className="space-y-2">
                <Label>Audit Note (optional)</Label>
                <Textarea
                  placeholder="Reason for manual correction / confirmation…"
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
                <Button
                  variant="outline"
                  className="flex-1"
                  onClick={() => navigate("/review")}
                >
                  Cancel
                </Button>
                <Button
                  className="flex-1"
                  onClick={handleSave}
                  disabled={!canSave}
                >
                  {saving
                    ? "Saving…"
                    : isMultiWbs
                      ? "Confirm Allocations"
                      : "Save Correction"}
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
    <div className="min-w-0">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-sm text-foreground mt-1 whitespace-pre-line break-words">
        {value || "—"}
      </p>
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
  return num.toLocaleString(undefined, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });
}