"""Build or update the local Chroma collection from the configured resume folder."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from backend.filesystem_service import SUPPORTED_EXTENSIONS


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--directory", default="data/resumes")
    args = parser.parse_args()
    directory = Path(args.directory).resolve()
    if not directory.is_dir():
        raise SystemExit(f"Resume directory does not exist: {directory}")

    from backend.ingestion import ingest_resume

    files = sorted(
        path
        for path in directory.iterdir()
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS
    )
    succeeded = 0
    for index, path in enumerate(files, start=1):
        result = ingest_resume(path)
        status = "OK" if result["success"] else "FAILED"
        print(f"[{index}/{len(files)}] {status} {path.name}")
        succeeded += int(result["success"])
    print(f"Ingestion complete: {succeeded}/{len(files)} files succeeded")
    raise SystemExit(0 if succeeded == len(files) else 1)


if __name__ == "__main__":
    main()
