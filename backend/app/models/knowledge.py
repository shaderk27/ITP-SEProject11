"""RAG knowledge store (W13-03A). Tables come from migrations/add_rag_knowledge.sql."""

from sqlalchemy import (
    ARRAY,
    BigInteger,
    Boolean,
    CHAR,
    Column,
    DateTime,
    ForeignKey,
    Integer,
    String,
    Text,
)
from sqlalchemy.sql import func
from pgvector.sqlalchemy import Vector

from app.database import Base


class KnowledgeDocument(Base):
    """An approved client document. visible_roles must be set explicitly."""

    __tablename__ = "knowledge_documents"

    document_id = Column(BigInteger, primary_key=True)
    title = Column(String(255), nullable=False)
    source_filename = Column(String(255), nullable=False)
    document_version = Column(String(50), nullable=False)
    visible_roles = Column(ARRAY(Text), nullable=False, default=list)
    is_active = Column(Boolean, nullable=False, default=True)
    uploaded_by = Column(BigInteger, ForeignKey("users.user_id"))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())


class KnowledgeChunk(Base):
    """One searchable piece of text: a document chunk or a PR-line card.

    Role scope is not stored here. PR-line chunks are scoped at query time
    through purchase_request_lines -> labs, documents through visible_roles.
    """

    __tablename__ = "knowledge_chunks"

    chunk_id = Column(BigInteger, primary_key=True)
    source_type = Column(String(20), nullable=False)  # "document" | "pr_line"
    document_id = Column(BigInteger, ForeignKey("knowledge_documents.document_id"))
    pr_line_id = Column(BigInteger, ForeignKey("purchase_request_lines.pr_line_id"))
    chunk_index = Column(Integer, nullable=False, default=0)
    source_ref = Column(String(255), nullable=False)
    content = Column(Text, nullable=False)
    content_hash = Column(CHAR(64), nullable=False)
    # No fixed dimension: always filter on embedding_model before comparing.
    embedding = Column(Vector(), nullable=False)
    embedding_model = Column(String(150), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now())
