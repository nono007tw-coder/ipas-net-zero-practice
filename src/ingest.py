from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path

from utils import chapter_number


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def ingest(source: Path, chapter_id: str, output_dir: Path, title: str = "") -> tuple[Path, Path]:
    number = chapter_number(chapter_id)
    if not source.exists() or not source.is_file():
        raise FileNotFoundError(f"Source file not found: {source}")
    if source.suffix.lower() != ".txt":
        raise ValueError("Ingest currently accepts UTF-8 plain-text .txt files only")

    source.read_text(encoding="utf-8-sig")
    output_dir.mkdir(parents=True, exist_ok=True)
    destination = output_dir / f"chapter_{number:03d}.txt"
    if source.resolve() != destination.resolve():
        shutil.copyfile(source, destination)

    manifest = {
        "chapter_id": chapter_id,
        "chapter_title": title,
        "file_name": destination.name,
        "sha256": sha256(destination),
        "byte_size": destination.stat().st_size,
        "content_modified": False,
    }
    manifest_path = output_dir / f"chapter_{number:03d}_manifest.json"
    manifest_path.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    return destination, manifest_path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Copy an authorized Brenner chapter text without modification.")
    parser.add_argument("--input", type=Path, required=True)
    parser.add_argument("--chapter", required=True, help="Chapter ID, for example CH001.")
    parser.add_argument("--title", default="")
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw_chapters"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    destination, manifest = ingest(args.input, args.chapter, args.output_dir, args.title)
    print(f"ingested unchanged source -> {destination}")
    print(f"wrote manifest -> {manifest}")


if __name__ == "__main__":
    main()
