"""
Show the closest PR-line cards and their distances for some questions, ignoring
role scope and the relevance cutoff. Use it to pick EMBEDDING_MAX_DISTANCE for
a new embedding model or new data: ask questions that should match and ones
that shouldn't, then set the cutoff between the two groups' best distances.

    cd backend
    python -m app.scripts.probe_knowledge "calibration equipment" "hello"
"""

from __future__ import annotations

import sys

from app.database import SessionLocal
from app.models.knowledge import KnowledgeChunk
from app.services import embedding_client

TOP_N = 3


def main(questions: list[str]) -> int:
    if not questions:
        print(__doc__)
        return 1
    if not embedding_client.embedding_configured():
        print("Embeddings are off. Set EMBEDDING_PROVIDER in the root .env first.")
        return 1

    model_id = embedding_client.embedding_model_id()
    print(
        f"Model {model_id}, current cutoff {embedding_client.embedding_max_distance()}"
    )
    with SessionLocal() as db:
        for question in questions:
            distance = KnowledgeChunk.embedding.cosine_distance(
                embedding_client.embed_query(question)
            )
            rows = (
                db.query(distance, KnowledgeChunk.source_ref, KnowledgeChunk.content)
                .filter(
                    KnowledgeChunk.embedding_model == model_id,
                    KnowledgeChunk.is_active.is_(True),
                )
                .order_by(distance)
                .limit(TOP_N)
            )
            print(f"\n{question!r}")
            for dist, ref, content in rows:
                lines = content.splitlines()
                item = lines[1] if len(lines) > 1 else ""
                print(f"  {dist:.3f}  {ref}  {item}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
