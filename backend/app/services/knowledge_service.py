"""
RAG knowledge store for Ask AI (W13-03A): PR-line cards and scoped vector search.

Each committed PR line gets one "card": a short text description of the line
(item, lab, category, purpose, amount, status) and its embedding. Cards let
Ask AI answer fuzzy questions SQL keyword matching can't, such as "did we buy
anything for 3D printing?". Totals, rankings and utilisation stay in the SQL
fact sheet (chatbot_service); cards are never used for arithmetic.

Role scope is applied in SQL before similarity ranking, using the same
_apply_role_scope as the chatbot's purchase context, so the two can't drift.
Scope comes from the DB-loaded user on every call, so a Lab IC reassignment
or a lab correction applies to the next search without re-indexing.
"""

from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from sqlalchemy.orm import Session

from app.database import SessionLocal
from app.models.auth import User
from app.models.config import Lab, LabGroup, SpendingCategory
from app.models.knowledge import KnowledgeChunk
from app.models.staging import PurchaseRequest, PurchaseRequestLine
from app.services import embedding_client
from app.services.chatbot_service import (
    CHATBOT_ALLOWED_ROLES,
    _apply_date_bounds,
    _apply_role_scope,
    _role_name,
)
from app.services.embedding_client import EmbeddingUnavailableError

logger = logging.getLogger(__name__)

PR_LINE_SOURCE = "pr_line"
CARD_CHUNK_INDEX = 0  # one card per PR line
EMBED_BATCH_SIZE = 64
DEFAULT_SEARCH_LIMIT = 8


@dataclass
class IndexResult:
    embedded: int = 0
    unchanged: int = 0
    deactivated: int = 0
    skipped_reason: str | None = None


@dataclass
class PRLineHit:
    pr_line_id: int
    source_ref: str
    content: str
    distance: float
    lab_id: int
    lab_name: str
    lab_group_name: str
    item_description: str
    pr_status: str | None
    request_date: date | None


# ─── Card text ───────────────────────────────────────────────────────────


def pr_line_source_ref(pr: PurchaseRequest, line: PurchaseRequestLine) -> str:
    return f"PR {pr.source_pr_number} line {line.line_no or '?'}"


def pr_line_card_text(
    pr: PurchaseRequest,
    line: PurchaseRequestLine,
    lab: Lab,
    group: LabGroup | None,
    category: SpendingCategory | None,
) -> str:
    """The text that gets embedded and later shown to the model as evidence.

    Requestor names are left out on purpose: they don't help match purchases,
    and leaving them out keeps personal data away from an external embedding
    provider.
    """
    lab_label = f"{lab.lab_name} ({lab.lab_code})" if lab.lab_code else lab.lab_name
    group_label = group.lab_group_name if group else "no lab group"
    parts = [
        pr_line_source_ref(pr, line),
        f"Item: {(line.item_description or '').strip() or 'No description'}",
        f"Lab: {lab_label}, lab group {group_label}",
        f"Category: {category.category_name if category else 'Uncategorised'}",
    ]
    if pr.purpose and pr.purpose.strip():
        parts.append(f"Purpose: {pr.purpose.strip()}")
    if pr.request_date:
        parts.append(f"Requested: {pr.request_date.isoformat()}")
    amount = Decimal(line.amount_gst or 0)
    parts.append(f"Amount: {line.currency_code or 'SGD'} {amount:,.2f} incl. GST")
    if line.qty is not None:
        parts.append(f"Quantity: {Decimal(line.qty).normalize():f}")
    parts.append(f"Status: {line.pr_status or 'unknown'}")
    return "\n".join(parts)


def _content_hash(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


# ─── Indexing ────────────────────────────────────────────────────────────


def index_pr_lines(db: Session, pr_ids: list[int] | None = None) -> IndexResult:
    """Create or refresh PR-line cards; pr_ids=None means every committed line.

    Only new or changed text is embedded (compared by content hash). Lines
    that lost their lab have their card deactivated so it can't be retrieved.
    Commits once per embedding batch, so a long backfill keeps its progress.
    """
    if not embedding_client.embedding_configured():
        return IndexResult(skipped_reason="Embeddings are not configured.")
    model_id = embedding_client.embedding_model_id()

    query = (
        db.query(PurchaseRequestLine, PurchaseRequest, Lab, LabGroup, SpendingCategory)
        .join(PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id)
        .outerjoin(Lab, Lab.lab_id == PurchaseRequestLine.lab_id)
        .outerjoin(LabGroup, LabGroup.lab_group_id == Lab.lab_group_id)
        .outerjoin(
            SpendingCategory,
            SpendingCategory.category_id == PurchaseRequestLine.category_id,
        )
        .order_by(PurchaseRequestLine.pr_line_id)
    )
    if pr_ids is not None:
        if not pr_ids:
            return IndexResult()
        query = query.filter(PurchaseRequestLine.pr_id.in_(pr_ids))
    rows = query.all()

    existing_query = db.query(KnowledgeChunk).filter(
        KnowledgeChunk.source_type == PR_LINE_SOURCE,
        KnowledgeChunk.embedding_model == model_id,
        KnowledgeChunk.chunk_index == CARD_CHUNK_INDEX,
    )
    if pr_ids is not None:
        existing_query = existing_query.filter(
            KnowledgeChunk.pr_line_id.in_([line.pr_line_id for line, *_ in rows])
        )
    existing = {chunk.pr_line_id: chunk for chunk in existing_query}

    result = IndexResult()
    pending: list[tuple[PurchaseRequestLine, str, str, str]] = []
    for line, pr, lab, group, category in rows:
        chunk = existing.get(line.pr_line_id)
        if lab is None:
            if chunk is not None and chunk.is_active:
                chunk.is_active = False
                result.deactivated += 1
            continue
        content = pr_line_card_text(pr, line, lab, group, category)
        content_hash = _content_hash(content)
        if chunk is not None and chunk.content_hash == content_hash:
            chunk.is_active = True
            result.unchanged += 1
            continue
        pending.append((line, pr_line_source_ref(pr, line), content, content_hash))

    db.commit()  # deactivations and reactivations

    for start in range(0, len(pending), EMBED_BATCH_SIZE):
        batch = pending[start : start + EMBED_BATCH_SIZE]
        vectors = embedding_client.embed_documents(
            [content for _, _, content, _ in batch]
        )
        for (line, source_ref, content, content_hash), vector in zip(batch, vectors):
            chunk = existing.get(line.pr_line_id)
            if chunk is None:
                chunk = KnowledgeChunk(
                    source_type=PR_LINE_SOURCE,
                    pr_line_id=line.pr_line_id,
                    chunk_index=CARD_CHUNK_INDEX,
                    embedding_model=model_id,
                )
                db.add(chunk)
            chunk.source_ref = source_ref
            chunk.content = content
            chunk.content_hash = content_hash
            chunk.embedding = vector
            chunk.is_active = True
        db.commit()
        result.embedded += len(batch)

    return result


def index_pr_lines_in_background(pr_ids: list[int]) -> None:
    """BackgroundTasks entry point after a batch commit. Never raises.

    A failure here only means the new lines aren't searchable yet; running
    `python -m app.scripts.index_knowledge` catches them up later.
    """
    if not embedding_client.embedding_configured():
        return
    with SessionLocal() as db:
        try:
            result = index_pr_lines(db, pr_ids)
            logger.info(
                "Indexed PR-line cards for %d PRs: %d embedded, %d unchanged, %d deactivated",
                len(pr_ids),
                result.embedded,
                result.unchanged,
                result.deactivated,
            )
        except EmbeddingUnavailableError as exc:
            db.rollback()
            logger.warning("PR-line indexing skipped: %s", exc)
        except Exception:
            db.rollback()
            logger.exception("PR-line indexing failed")


# ─── Search ──────────────────────────────────────────────────────────────


def search_pr_lines(
    db: Session,
    current_user: User,
    question: str,
    limit: int = DEFAULT_SEARCH_LIMIT,
    start: date | None = None,
    end: date | None = None,
    approved_only: bool = True,
    status_prefix: str | None = None,
    max_distance: float | None = None,
) -> list[PRLineHit]:
    """Most similar PR-line cards the user is allowed to see, closest first.

    approved_only matches the default fact sheet purchase sample. A specific
    status_prefix, such as "pending", overrides it for explicit status-aware
    questions. Hits further than max_distance (default:
    embedding_client.embedding_max_distance()) are dropped, so a question
    unrelated to any purchase returns nothing rather than the "least bad" lines.

    Raises EmbeddingUnavailableError when embeddings are off or failing, so
    the caller can fall back to the SQL fact sheet alone.
    """
    if _role_name(current_user) not in CHATBOT_ALLOWED_ROLES:
        return []
    if not question.strip():
        return []

    query_vector = embedding_client.embed_query(question)
    distance_expr = KnowledgeChunk.embedding.cosine_distance(query_vector)
    distance = distance_expr.label("distance")
    cutoff = (
        max_distance
        if max_distance is not None
        else embedding_client.embedding_max_distance()
    )

    query = (
        db.query(
            KnowledgeChunk,
            PurchaseRequestLine,
            PurchaseRequest,
            Lab,
            LabGroup,
            distance,
        )
        .join(
            PurchaseRequestLine,
            PurchaseRequestLine.pr_line_id == KnowledgeChunk.pr_line_id,
        )
        .join(PurchaseRequest, PurchaseRequest.pr_id == PurchaseRequestLine.pr_id)
        .join(Lab, Lab.lab_id == PurchaseRequestLine.lab_id)
        .join(LabGroup, LabGroup.lab_group_id == Lab.lab_group_id)
        .filter(KnowledgeChunk.source_type == PR_LINE_SOURCE)
        .filter(KnowledgeChunk.is_active.is_(True))
        .filter(KnowledgeChunk.embedding_model == embedding_client.embedding_model_id())
        .filter(LabGroup.lab_group_name != "General")
    )
    if status_prefix:
        query = query.filter(PurchaseRequestLine.pr_status.ilike(f"{status_prefix}%"))
    elif approved_only:
        query = query.filter(PurchaseRequestLine.pr_status.ilike("approved%"))
    if cutoff is not None:
        query = query.filter(distance_expr <= cutoff)
    query = _apply_date_bounds(query, start, end)
    query = _apply_role_scope(query, current_user)

    return [
        PRLineHit(
            pr_line_id=int(line.pr_line_id),
            source_ref=chunk.source_ref,
            content=chunk.content,
            distance=float(dist),
            lab_id=int(lab.lab_id),
            lab_name=lab.lab_name,
            lab_group_name=group.lab_group_name,
            item_description=line.item_description or "",
            pr_status=line.pr_status,
            request_date=pr.request_date,
        )
        for chunk, line, pr, lab, group, dist in query.order_by(distance).limit(limit)
    ]
