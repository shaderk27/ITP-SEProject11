"""
System-derived extras for the PR Records export.

The person who uploads a PR file already has every column of it, so a
re-dump of those columns tells them nothing new. What they do NOT have is
what the system worked out after the upload:

  - Classification trail — how each line got its lab / category (auto-match
    or manual review), who reviewed it and which upload it came from.
  - Change history       — what changed on a PR between uploads (pr_versions).
  - Budget impact        — where each PR left its lab's FY budget, and which
    PR pushed a lab past an alert threshold.

Everything is keyed off the PR list the caller passes in, which records.py
has already role-scoped, so nothing here can widen what a user can see.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Sequence

from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.models.auth import User
from app.models.config import Budget, BudgetPeriod, LabGroup
from app.models.staging import (
    PRVersion,
    PurchaseRequest,
    PurchaseRequestLine,
    ReviewAction,
    ReviewQueueItem,
    StagingPRHeader,
    StagingPRLine,
    UploadBatch,
)

# Same thresholds the budget alert emails use (labs.notified_50/80/95/100).
ALERT_THRESHOLDS = (50, 80, 95, 100)

# persistence_repository writes this reason on a re-uploaded line that
# already exists in the final tables — it isn't where the classification
# actually came from, so the trail looks past it to the original upload.
_PRESERVED_REASON_PREFIX = "Existing committed line found"


@dataclass
class TrailEntry:
    method: str
    reason: str
    uploaded_lab_text: str
    uploaded_category: str
    reviewed_by: str
    reviewed_at: datetime | None
    review_comment: str
    upload_count: int
    source_file: str
    uploaded_by: str
    uploaded_at: datetime | None


@dataclass
class ChangeEntry:
    changed_at: datetime | None
    pr_number: str
    source_file: str
    changed_by: str
    field: str
    old_value: str
    new_value: str


@dataclass
class ImpactEntry:
    pr_date: date | None
    pr_number: str
    requestor: str
    lab_group: str
    lab: str
    fy_label: str
    status: str
    amount: float
    counted_amount: float
    budget: float | None
    used_before: float | None
    used_after: float | None
    pct_after: float | None
    balance_after: float | None
    flag: str


@dataclass
class ExportInsights:
    trail: dict[int, TrailEntry] = field(default_factory=dict)  # by pr_line_id
    changes: list[ChangeEntry] = field(default_factory=list)
    impact: list[ImpactEntry] = field(default_factory=list)


def build_export_insights(
    db: Session, prs: Sequence[Any], role_name: str
) -> ExportInsights:
    """Gather the trail / history / budget-impact data for the given PRs."""
    if not prs:
        return ExportInsights()
    group_names = {g.lab_group_id: g.lab_group_name for g in db.query(LabGroup).all()}
    return ExportInsights(
        trail=_classification_trail(db, prs),
        changes=_change_history(db, prs, role_name, group_names),
        impact=_budget_impact(db, prs),
    )


def counts_toward_budget(status: str | None) -> bool:
    """Approved + Pending lines consume budget — same rule as the dashboard."""
    s = (status or "").strip().lower()
    return s.startswith("approved") or s.startswith("pending")


# ─── 1. Classification trail ─────────────────────────────────────────────
def _classification_trail(db: Session, prs: Sequence[Any]) -> dict[int, TrailEntry]:
    lines = [(pr.source_pr_number, line) for pr in prs for line in pr.lines]
    if not lines:
        return {}

    # Every committed upload of these PRs, oldest first.
    staged = (
        db.query(
            StagingPRLine,
            StagingPRHeader.source_pr_number,
            UploadBatch.filename,
            UploadBatch.uploaded_at,
            User.full_name,
        )
        .join(
            StagingPRHeader,
            StagingPRHeader.staging_header_id == StagingPRLine.staging_header_id,
        )
        .join(UploadBatch, UploadBatch.batch_id == StagingPRHeader.batch_id)
        .outerjoin(User, User.user_id == UploadBatch.uploaded_by)
        .filter(StagingPRHeader.source_pr_number.in_({n for n, _ in lines}))
        .filter(UploadBatch.upload_status == "committed")
        .order_by(StagingPRLine.staging_line_id)
        .all()
    )
    # Row numbers shift between files, so the same line across uploads is
    # tied together by its line_identity_key (what the commit step matches on).
    identity_of: dict[int, tuple[str, str]] = {}
    by_identity: dict[tuple[str, str], list[tuple]] = defaultdict(list)
    by_row: dict[tuple[str, int | None], list[tuple]] = defaultdict(list)
    for line, number, filename, uploaded_at, uploader in staged:
        upload = (line, filename, uploaded_at, uploader)
        raw = line.raw_line_json if isinstance(line.raw_line_json, dict) else {}
        key = (
            number,
            str(raw.get("line_identity_key") or f"row:{line.source_line_no}"),
        )
        identity_of[line.staging_line_id] = key
        by_identity[key].append(upload)
        by_row[(number, line.source_line_no)].append(upload)

    # Latest manual review per staging line.
    staging_ids = [row[0].staging_line_id for row in staged]
    reviews: dict[int, tuple[ReviewAction, str]] = {}
    if staging_ids:
        for staging_line_id, action, reviewer in (
            db.query(ReviewQueueItem.staging_line_id, ReviewAction, User.full_name)
            .join(
                ReviewAction,
                ReviewAction.review_queue_id == ReviewQueueItem.review_queue_id,
            )
            .outerjoin(User, User.user_id == ReviewAction.reviewed_by)
            .filter(ReviewQueueItem.staging_line_id.in_(staging_ids))
            .order_by(ReviewAction.reviewed_at, ReviewAction.review_action_id)
            .all()
        ):
            reviews[staging_line_id] = (action, reviewer or "")

    trail: dict[int, TrailEntry] = {}
    for number, committed in lines:
        identity = identity_of.get(committed.source_staging_line_id)
        history = (
            by_identity[identity]
            if identity
            else by_row.get((number, committed.line_no))
        )
        if not history:
            continue
        origin = next(
            (
                h
                for h in history
                if not (h[0].match_reason or "").startswith(_PRESERVED_REASON_PREFIX)
            ),
            history[0],
        )
        latest = history[-1]
        review = None
        for h in history:
            review = reviews.get(h[0].staging_line_id, review)

        origin_line = origin[0]
        if review is not None:
            method = "Manually reviewed"
        elif origin_line.classification_status == "confident":
            method = "Auto-matched"
        else:
            method = "Auto (fell back to General)"

        trail[committed.pr_line_id] = TrailEntry(
            method=method,
            reason=origin_line.match_reason or "",
            uploaded_lab_text=origin_line.raw_lab_text or "",
            uploaded_category=origin_line.raw_pr_category or "",
            reviewed_by=review[1] if review else "",
            reviewed_at=_naive(review[0].reviewed_at) if review else None,
            review_comment=(review[0].review_comment or "") if review else "",
            upload_count=len(history),
            source_file=latest[1] or "",
            uploaded_by=latest[3] or "",
            uploaded_at=_naive(latest[2]),
        )
    return trail


# ─── 2. Change history ───────────────────────────────────────────────────
_HEADER_FIELDS: list[tuple[str, str]] = [
    ("pr_status", "PR Status"),
    ("grand_total_sgd", "PR Total"),
    ("line_count", "Number of Lines"),
    ("requestor_name", "Requestor"),
    ("wbs_code", "WBS Code"),
    ("lab_group_id", "Lab Group"),
]
_LINE_STATUS_FIELDS: list[tuple[str, str]] = [
    ("po_number", "PO Number"),
    ("po_status", "PO Status"),
]
# PR-wide totals include other labs' lines, which a Lab IC must not see.
_LABIC_HIDDEN_FIELDS = {"grand_total_sgd", "line_count"}


def _change_history(
    db: Session,
    prs: Sequence[Any],
    role_name: str,
    group_names: dict[int, str],
) -> list[ChangeEntry]:
    pr_ids = [pr.pr_id for pr in prs]
    versions = (
        db.query(
            PRVersion,
            PurchaseRequest.source_pr_number,
            UploadBatch.filename,
            User.full_name,
        )
        .join(PurchaseRequest, PurchaseRequest.pr_id == PRVersion.pr_id)
        .outerjoin(UploadBatch, UploadBatch.batch_id == PRVersion.batch_id)
        .outerjoin(User, User.user_id == PRVersion.changed_by)
        .filter(PRVersion.pr_id.in_(pr_ids))
        .filter(PRVersion.change_type == "updated")
        .order_by(PRVersion.changed_at, PRVersion.version_id)
        .all()
    )

    def show(key: str, raw: Any) -> str:
        if raw is None or raw == "":
            return "(blank)"
        if key == "lab_group_id":
            return group_names.get(raw, str(raw))
        if key == "grand_total_sgd":
            try:
                return f"SGD {Decimal(str(raw)):,.2f}"
            except ArithmeticError:
                return str(raw)
        return str(raw)

    entries: list[ChangeEntry] = []
    for version, number, filename, changed_by in versions:
        old = version.old_data or {}
        new = version.new_data or {}
        base = {
            "changed_at": _naive(version.changed_at),
            "pr_number": number,
            "source_file": filename or "",
            "changed_by": changed_by or "",
        }
        for key, label in _HEADER_FIELDS:
            if role_name == "labic" and key in _LABIC_HIDDEN_FIELDS:
                continue
            if key not in old and key not in new:
                continue
            if _same(old.get(key), new.get(key)):
                continue
            entries.append(
                ChangeEntry(
                    **base,
                    field=label,
                    old_value=show(key, old.get(key)),
                    new_value=show(key, new.get(key)),
                )
            )

        # Per-line PO updates aren't tagged with a line number, so they can't
        # be narrowed to a Lab IC's own lines — only show them to wider roles.
        if role_name == "labic":
            continue
        seen: set[tuple[str, str, str]] = set()
        for before, after in zip(
            old.get("status_updates") or [], new.get("status_updates") or []
        ):
            for key, label in _LINE_STATUS_FIELDS:
                change = (label, show(key, before.get(key)), show(key, after.get(key)))
                if change[1] == change[2] or change in seen:
                    continue
                seen.add(change)
                entries.append(
                    ChangeEntry(
                        **base,
                        field=change[0],
                        old_value=change[1],
                        new_value=change[2],
                    )
                )
    return entries


def _same(a: Any, b: Any) -> bool:
    try:
        return Decimal(str(a)) == Decimal(str(b))
    except ArithmeticError:
        return (a or "") == (b or "")


# ─── 3. Budget impact ────────────────────────────────────────────────────
def _budget_impact(db: Session, prs: Sequence[Any]) -> list[ImpactEntry]:
    line_ids = [line.pr_line_id for pr in prs for line in pr.lines]
    if not line_ids:
        return []
    lab_of_line = dict(
        db.query(PurchaseRequestLine.pr_line_id, PurchaseRequestLine.lab_id)
        .filter(PurchaseRequestLine.pr_line_id.in_(line_ids))
        .all()
    )
    lab_ids = {lab_id for lab_id in lab_of_line.values() if lab_id is not None}
    if not lab_ids:
        return []

    # FY budget per (FY start year, lab). General lab-group budgets are left
    # out, matching the dashboard breakdown.
    budgets: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
    for year_no, lab_id, amount in (
        db.query(BudgetPeriod.year_no, Budget.lab_id, Budget.budget_amount)
        .join(BudgetPeriod, BudgetPeriod.period_id == Budget.period_id)
        .join(LabGroup, LabGroup.lab_group_id == Budget.lab_group_id)
        .filter(LabGroup.lab_group_name != "General")
        .filter(Budget.lab_id.in_(lab_ids))
        .all()
    ):
        budgets[(year_no, lab_id)] += Decimal(str(amount or 0))
    fy_names = dict(db.query(BudgetPeriod.year_no, BudgetPeriod.period_name).all())

    # Running Approved + Pending spend per lab across the WHOLE fiscal year,
    # in PR-date order — not just the exported rows — so "used before" is
    # still right when the page is filtered by date or search. lab_ids only
    # holds labs the caller can already see, so this stays role-scoped.
    ledger = (
        db.query(
            PurchaseRequestLine.pr_id,
            PurchaseRequestLine.lab_id,
            PurchaseRequestLine.amount_gst,
            PurchaseRequest.request_date,
        )
        .join(PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id)
        .filter(PurchaseRequestLine.lab_id.in_(lab_ids))
        .filter(PurchaseRequest.request_date.isnot(None))
        .filter(
            or_(
                PurchaseRequestLine.pr_status.ilike("approved%"),
                PurchaseRequestLine.pr_status.ilike("pending%"),
            )
        )
        .order_by(
            PurchaseRequest.request_date,
            PurchaseRequest.source_pr_number,
            PurchaseRequestLine.line_no,
        )
        .all()
    )
    running: dict[tuple[int, int], Decimal] = defaultdict(Decimal)
    position: dict[tuple[int, int], list[Decimal]] = {}  # (pr, lab) -> [before, after]
    for pr_id, lab_id, amount, request_date in ledger:
        key = (_fy_year(request_date), lab_id)
        slot = position.setdefault((pr_id, lab_id), [running[key], running[key]])
        running[key] += Decimal(str(amount or 0))
        slot[1] = running[key]

    entries: list[ImpactEntry] = []
    for pr in prs:
        pr_date = _as_date(pr.request_date)
        by_lab: dict[int, list[Any]] = defaultdict(list)
        for line in pr.lines:
            lab_id = lab_of_line.get(line.pr_line_id)
            if lab_id is not None:
                by_lab[lab_id].append(line)
        for lab_id, lines in by_lab.items():
            amount = sum(_num(line.amount_gst) for line in lines)
            counted = sum(
                _num(line.amount_gst)
                for line in lines
                if counts_toward_budget(line.pr_status)
            )
            statuses = sorted({line.pr_status or "(blank)" for line in lines})
            entry = ImpactEntry(
                pr_date=pr_date,
                pr_number=pr.source_pr_number,
                requestor=pr.requestor_name or "",
                lab_group=pr.lab_group_name or "",
                lab=lines[0].lab_name or "",
                fy_label="",
                status=", ".join(statuses),
                amount=amount,
                counted_amount=counted,
                budget=None,
                used_before=None,
                used_after=None,
                pct_after=None,
                balance_after=None,
                flag="",
            )
            entries.append(entry)

            if pr_date is None:
                entry.flag = "No PR date — can't place on the budget timeline"
                continue
            fy = _fy_year(pr_date)
            entry.fy_label = fy_names.get(fy, f"FY{fy}")
            slot = position.get((pr.pr_id, lab_id))
            if slot is None:
                entry.flag = f"Not counted ({entry.status})"
                continue

            before, after = slot
            entry.used_before = float(before)
            entry.used_after = float(after)
            budget = budgets.get((fy, lab_id))
            if not budget:
                entry.flag = "No budget set for this lab"
                continue
            entry.budget = float(budget)
            entry.balance_after = float(budget - after)
            before_pct = float(before / budget * 100)
            entry.pct_after = float(after / budget * 100)
            entry.flag = _threshold_flag(before_pct, entry.pct_after)

    entries.sort(key=lambda e: (e.pr_date or date.max, e.pr_number, e.lab))
    return entries


def _threshold_flag(before_pct: float, after_pct: float) -> str:
    crossed = [t for t in ALERT_THRESHOLDS if before_pct < t <= after_pct]
    if crossed and crossed[-1] == 100:
        return "Pushed lab over budget" if after_pct > 100 else "Used up the lab budget"
    if crossed:
        return f"Crossed {crossed[-1]}% alert"
    if before_pct >= 100:
        return "Lab was already over budget"
    return ""


# ─── Helpers ─────────────────────────────────────────────────────────────
def _fy_year(d: date) -> int:
    """Budget cycle runs 1 April → 31 March, named by its starting year."""
    return d.year if d.month >= 4 else d.year - 1


def _as_date(raw: Any) -> date | None:
    if not raw:
        return None
    if isinstance(raw, date):
        return raw
    try:
        return date.fromisoformat(str(raw)[:10])
    except ValueError:
        return None


def _num(raw: Any) -> float:
    try:
        return float(Decimal(str(raw)))
    except (ArithmeticError, ValueError):
        return 0.0


def _naive(value: datetime | None) -> datetime | None:
    """openpyxl can't write tz-aware datetimes; show them in server local time."""
    if value is None:
        return None
    return value.astimezone().replace(tzinfo=None) if value.tzinfo else value
