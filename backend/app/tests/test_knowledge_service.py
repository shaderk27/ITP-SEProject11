"""PR-line RAG cards: card text, indexing and role-scoped vector search.

DB tests run inside the conftest savepoint (nothing persists) and need
migrations/add_rag_knowledge.sql applied. Embeddings are faked with keyword
vectors, so no model or network is used.
"""

from __future__ import annotations

import contextlib
import uuid
from datetime import date
from decimal import Decimal

import pytest
from sqlalchemy import inspect

from app.models.auth import Role, User
from app.models.config import Lab, LabGroup, LabIcAssignment, SpendingCategory
from app.models.knowledge import KnowledgeChunk
from app.models.staging import PurchaseRequest, PurchaseRequestLine
from app.services import embedding_client, knowledge_service
from app.services.embedding_client import EmbeddingUnavailableError
from app.services.knowledge_service import (
    index_pr_lines,
    pr_line_card_text,
    search_pr_lines,
)

VOCAB = ["oscilloscope", "filament", "ethanol", "pipette", "chair"]
FAKE_MODEL = "test:fake-keywords"


def _fake_vector(text: str) -> list[float]:
    lowered = text.lower()
    # Trailing constant keeps every vector non-zero (cosine needs a length).
    return [float(lowered.count(word)) for word in VOCAB] + [0.1]


class FakeEmbedder:
    def __init__(self):
        self.document_calls: list[list[str]] = []

    def embed_documents(self, texts):
        self.document_calls.append(list(texts))
        return [_fake_vector(t) for t in texts]

    @property
    def embedded_count(self) -> int:
        return sum(len(call) for call in self.document_calls)


@pytest.fixture
def fake_embeddings(monkeypatch) -> FakeEmbedder:
    fake = FakeEmbedder()
    monkeypatch.setattr(embedding_client, "embedding_configured", lambda: True)
    monkeypatch.setattr(embedding_client, "embedding_model_id", lambda: FAKE_MODEL)
    # Fake vectors have no calibrated cutoff; tests that want one set it.
    monkeypatch.setattr(embedding_client, "embedding_max_distance", lambda: None)
    monkeypatch.setattr(embedding_client, "embed_documents", fake.embed_documents)
    monkeypatch.setattr(embedding_client, "embed_query", _fake_vector)
    return fake


@pytest.fixture
def rag_tables(db):
    if not inspect(db.get_bind()).has_table("knowledge_chunks"):
        pytest.skip("Run backend/migrations/add_rag_knowledge.sql first.")


def _uid() -> str:
    return uuid.uuid4().hex[:8]


def _group(db, name: str) -> LabGroup:
    group = LabGroup(lab_group_name=name, wbs_code=f"WBS-{_uid()}")
    db.add(group)
    db.flush()
    return group


def _lab(db, group: LabGroup, name: str) -> Lab:
    lab = Lab(lab_group_id=group.lab_group_id, lab_name=name, lab_code=f"T-{_uid()}")
    db.add(lab)
    db.flush()
    return lab


def _line(
    db, lab: Lab | None, description: str, status: str = "approved"
) -> PurchaseRequestLine:
    pr = PurchaseRequest(
        source_pr_number=f"T{_uid()}",
        request_date=date(2026, 5, 4),
        purpose="Teaching lab restock",
    )
    db.add(pr)
    db.flush()
    line = PurchaseRequestLine(
        pr_id=pr.pr_id,
        line_no=1,
        item_description=description,
        qty=Decimal("2"),
        amount_gst=Decimal("1234.50"),
        lab_id=lab.lab_id if lab else None,
        pr_status=status,
    )
    db.add(line)
    db.flush()
    return line


def _user(db, role_name: str, lab_group: LabGroup | None = None) -> User:
    role = db.query(Role).filter(Role.role_name == role_name).one()
    user = User(
        role_id=role.role_id,
        full_name=f"RAG test {role_name}",
        email=f"rag-{_uid()}@test.com",
        password_hash="x",
        lab_group_id=lab_group.lab_group_id if lab_group else None,
    )
    db.add(user)
    db.flush()
    return user


@pytest.fixture
def world(db, rag_tables, fake_embeddings):
    """Two groups: G1 = labs A + B, G2 = lab C. Plus a lab-less line and a General line."""
    g1, g2 = _group(db, f"RAG G1 {_uid()}"), _group(db, f"RAG G2 {_uid()}")
    general = db.query(LabGroup).filter(LabGroup.lab_group_name == "General").first()
    general = general or _group(db, "General")
    lab_a, lab_b, lab_c = (
        _lab(db, g1, "Lab A"),
        _lab(db, g1, "Lab B"),
        _lab(db, g2, "Lab C"),
    )
    lab_general = _lab(db, general, "General fallback lab")

    lines = {
        "a": _line(db, lab_a, "Oscilloscope 100MHz"),
        "b": _line(db, lab_b, "PLA filament spools"),
        "c": _line(db, lab_c, "Oscilloscope 200MHz"),
        "general": _line(db, lab_general, "Oscilloscope probe set"),
        "no_lab": _line(db, None, "Oscilloscope spare"),
    }

    labic = _user(db, "labic")
    for lab, primary in ((lab_a, True), (lab_b, False)):
        db.add(
            LabIcAssignment(
                lab_id=lab.lab_id, user_id=labic.user_id, is_primary=primary
            )
        )
    db.flush()
    db.refresh(labic)

    return {
        "lines": lines,
        "labs": {"a": lab_a, "b": lab_b, "c": lab_c},
        "labic": labic,
        "teamlead_g2": _user(db, "teamlead", g2),
        "admin": _user(db, "admin"),
        "pr_ids": [line.pr_id for line in lines.values()],
    }


def _hit_line_ids(hits) -> list[int]:
    return [hit.pr_line_id for hit in hits]


# ─── Card text (no DB) ───────────────────────────────────────────────────


def test_card_text_has_search_fields_and_no_requestor():
    pr = PurchaseRequest(
        source_pr_number="4500012345",
        requestor_name="Jane Tan",
        request_date=date(2026, 5, 4),
        purpose="Signals lab upgrade",
    )
    line = PurchaseRequestLine(
        line_no=2,
        item_description="Tektronix oscilloscope",
        qty=Decimal("1.00"),
        amount_gst=Decimal("2400"),
        currency_code="SGD",
        pr_status="approved",
    )
    lab = Lab(lab_name="Embedded Lab", lab_code="E2-02-02")
    group = LabGroup(lab_group_name="ICT")
    category = SpendingCategory(category_name="Equipment")

    text = pr_line_card_text(pr, line, lab, group, category)

    assert text.splitlines()[0] == "PR 4500012345 line 2"
    for expected in (
        "Item: Tektronix oscilloscope",
        "Lab: Embedded Lab (E2-02-02), lab group ICT",
        "Category: Equipment",
        "Purpose: Signals lab upgrade",
        "Requested: 2026-05-04",
        "Amount: SGD 2,400.00 incl. GST",
        "Quantity: 1",
        "Status: approved",
    ):
        assert expected in text
    assert "Jane" not in text


# ─── Indexing ────────────────────────────────────────────────────────────


def test_index_embeds_only_new_or_changed_lines(db, world, fake_embeddings):
    first = index_pr_lines(db, world["pr_ids"])
    # Every line with a lab gets a card (General is indexed but never searched).
    assert (first.embedded, first.unchanged) == (4, 0)

    again = index_pr_lines(db, world["pr_ids"])
    assert (again.embedded, again.unchanged) == (0, 4)

    world["lines"]["c"].pr_status = "rejected"
    db.flush()
    changed = index_pr_lines(db, world["pr_ids"])
    assert (changed.embedded, changed.unchanged) == (1, 3)

    chunk = (
        db.query(KnowledgeChunk)
        .filter(KnowledgeChunk.pr_line_id == world["lines"]["c"].pr_line_id)
        .all()
    )
    assert len(chunk) == 1  # updated in place, not duplicated
    assert "Status: rejected" in chunk[0].content
    assert fake_embeddings.embedded_count == 5


def test_line_that_loses_its_lab_is_deactivated(db, world):
    index_pr_lines(db, world["pr_ids"])
    line_a = world["lines"]["a"]
    line_a.lab_id = None
    db.flush()

    result = index_pr_lines(db, world["pr_ids"])

    assert result.deactivated == 1
    chunk = (
        db.query(KnowledgeChunk)
        .filter(KnowledgeChunk.pr_line_id == line_a.pr_line_id)
        .one()
    )
    assert chunk.is_active is False


def test_embeddings_off_skips_indexing_and_search_raises(db, rag_tables, monkeypatch):
    monkeypatch.setenv("EMBEDDING_PROVIDER", "")
    assert index_pr_lines(db).skipped_reason
    admin = _user(db, "admin")
    with pytest.raises(EmbeddingUnavailableError):
        search_pr_lines(db, admin, "oscilloscope")


def test_background_indexing_never_raises(db, rag_tables, fake_embeddings, monkeypatch):
    monkeypatch.setattr(
        knowledge_service, "SessionLocal", lambda: contextlib.nullcontext(db)
    )

    def boom(*args, **kwargs):
        raise RuntimeError("db exploded")

    monkeypatch.setattr(knowledge_service, "index_pr_lines", boom)
    knowledge_service.index_pr_lines_in_background([1, 2])  # must not raise


# ─── Role-scoped search ──────────────────────────────────────────────────


def test_lab_ic_only_retrieves_assigned_labs(db, world):
    index_pr_lines(db, world["pr_ids"])
    lines = world["lines"]

    hits = search_pr_lines(db, world["labic"], "oscilloscope")

    # Lab C's oscilloscope matches too, but it belongs to another group.
    assert _hit_line_ids(hits) == [lines["a"].pr_line_id, lines["b"].pr_line_id]
    assert {hit.lab_id for hit in hits} <= {
        world["labs"]["a"].lab_id,
        world["labs"]["b"].lab_id,
    }


def test_lab_ic_reassignment_applies_to_next_search(db, world):
    index_pr_lines(db, world["pr_ids"])
    labic = world["labic"]
    db.query(LabIcAssignment).filter(
        LabIcAssignment.user_id == labic.user_id,
        LabIcAssignment.lab_id == world["labs"]["a"].lab_id,
    ).delete()
    db.add(LabIcAssignment(lab_id=world["labs"]["c"].lab_id, user_id=labic.user_id))
    db.flush()
    db.expire(labic)  # what a fresh request would load

    hit_ids = _hit_line_ids(search_pr_lines(db, labic, "oscilloscope"))

    assert world["lines"]["a"].pr_line_id not in hit_ids
    assert hit_ids[0] == world["lines"]["c"].pr_line_id


def test_team_lead_only_retrieves_own_group(db, world):
    index_pr_lines(db, world["pr_ids"])

    hits = search_pr_lines(db, world["teamlead_g2"], "oscilloscope")

    assert _hit_line_ids(hits) == [world["lines"]["c"].pr_line_id]


def test_admin_retrieves_all_except_general_and_lab_less(db, world):
    index_pr_lines(db, world["pr_ids"])
    lines = world["lines"]

    hit_ids = _hit_line_ids(search_pr_lines(db, world["admin"], "oscilloscope"))

    assert set(hit_ids) == {
        lines["a"].pr_line_id,
        lines["b"].pr_line_id,
        lines["c"].pr_line_id,
    }


def test_unknown_role_and_blank_question_get_nothing(db, world):
    index_pr_lines(db, world["pr_ids"])
    no_role = User(full_name="x", email="x@test.com", password_hash="x")

    assert search_pr_lines(db, no_role, "oscilloscope") == []
    assert search_pr_lines(db, world["admin"], "   ") == []


def test_search_respects_date_bounds(db, world):
    index_pr_lines(db, world["pr_ids"])

    hits = search_pr_lines(
        db,
        world["admin"],
        "oscilloscope",
        start=date(2027, 4, 1),
        end=date(2028, 3, 31),
    )

    assert hits == []


def test_only_approved_lines_by_default(db, world):
    pending = _line(
        db, world["labs"]["a"], "Oscilloscope 50MHz", status="Pending Approval"
    )
    index_pr_lines(db, world["pr_ids"] + [pending.pr_id])

    default_ids = _hit_line_ids(search_pr_lines(db, world["admin"], "oscilloscope"))
    all_ids = _hit_line_ids(
        search_pr_lines(db, world["admin"], "oscilloscope", approved_only=False)
    )

    assert pending.pr_line_id not in default_ids
    assert pending.pr_line_id in all_ids


def test_distance_cutoff_drops_unrelated_lines(db, world, monkeypatch):
    index_pr_lines(db, world["pr_ids"])
    lines = world["lines"]

    # No cutoff: the filament line still comes back as the "least bad" match.
    assert lines["b"].pr_line_id in _hit_line_ids(
        search_pr_lines(db, world["labic"], "oscilloscope")
    )

    explicit = search_pr_lines(db, world["labic"], "oscilloscope", max_distance=0.5)
    assert _hit_line_ids(explicit) == [lines["a"].pr_line_id]

    monkeypatch.setattr(embedding_client, "embedding_max_distance", lambda: 0.5)
    from_config = search_pr_lines(db, world["labic"], "oscilloscope")
    assert _hit_line_ids(from_config) == [lines["a"].pr_line_id]

    assert search_pr_lines(db, world["labic"], "office chair") == []
