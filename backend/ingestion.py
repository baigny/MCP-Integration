"""Resume-to-Chroma ingestion reused by batch and watch workflows."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from backend import chunking, embeddings, fs_tools, metadata_extractor, vector_store


def ingest_resume(filepath: str | Path) -> dict[str, Any]:
    """Extract, chunk, embed, and upsert one resume without raising to callers."""
    path = Path(filepath)
    try:
        read_result = fs_tools.read_file(str(path))
        if not read_result.get("success"):
            return {
                "success": False,
                "data": None,
                "error": {"code": "read_failed", "message": read_result.get("error", "Read failed")},
            }

        resume_text = read_result["content"]
        metadata = metadata_extractor.extract_metadata(resume_text)
        chunks = chunking.chunk_resume(resume_text)
        vectors = embeddings.embed_texts([chunk["text"] for chunk in chunks])
        records = [
            {
                "id": f"{path.name}::{index}::{chunk['section']}",
                "text": chunk["text"],
                "embedding": vector,
                "metadata": {
                    "source_file": path.name,
                    "section": chunk["section"],
                    "name": metadata["name"],
                    "skills": ", ".join(metadata["skills"]),
                    "years_experience": metadata["years_experience"],
                    "education": metadata["education"],
                },
            }
            for index, (chunk, vector) in enumerate(zip(chunks, vectors))
        ]
        vector_store.upsert_chunks(records)
        return {
            "success": True,
            "data": {"path": str(path.resolve()), "chunks": len(records)},
            "error": None,
        }
    except Exception:
        return {
            "success": False,
            "data": None,
            "error": {"code": "ingest_failed", "message": "Resume ingestion failed"},
        }
