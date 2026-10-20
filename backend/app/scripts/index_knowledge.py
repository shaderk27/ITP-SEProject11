"""
Build or refresh Ask AI's PR-line search cards for every committed PR line.

Batch commits index their own lines in the background; run this to backfill
existing data, after changing EMBEDDING_PROVIDER / EMBEDDING_MODEL, or after
renaming labs or categories. Safe to re-run: unchanged lines are skipped.

    cd backend
    python -m app.scripts.index_knowledge
"""

from __future__ import annotations

import sys
import time

from app.database import SessionLocal
from app.services import embedding_client
from app.services.embedding_client import EmbeddingUnavailableError
from app.services.knowledge_service import index_pr_lines


def main() -> int:
    if not embedding_client.embedding_configured():
        print(
            "Embeddings are off. Set EMBEDDING_PROVIDER (and EMBEDDING_API_KEY "
            "for 'api') in the root .env first."
        )
        return 1

    print(f"Indexing PR lines with {embedding_client.embedding_model_id()} ...")
    started = time.monotonic()
    with SessionLocal() as db:
        try:
            result = index_pr_lines(db)
        except EmbeddingUnavailableError as exc:
            print(f"Stopped: {exc} Lines indexed before this point were kept.")
            return 1
    print(
        f"Done in {time.monotonic() - started:.1f}s: {result.embedded} embedded, "
        f"{result.unchanged} unchanged, {result.deactivated} deactivated."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
