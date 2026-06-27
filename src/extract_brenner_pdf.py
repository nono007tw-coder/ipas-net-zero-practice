from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from pypdf import PdfReader


CHAPTER_RE = re.compile(r"^(\d{1,3})\s+(.+)$")


@dataclass(slots=True)
class Bookmark:
    title: str
    pdf_page: int
    depth: int


@dataclass(slots=True)
class Chapter:
    number: int
    chapter_id: str
    title: str
    start_pdf_page: int
    end_pdf_page: int
    sections: list[Bookmark]

    def to_catalog_entry(self) -> dict[str, Any]:
        return {
            "chapter_number": self.number,
            "chapter_id": self.chapter_id,
            "chapter_title": self.title,
            "start_pdf_page": self.start_pdf_page,
            "end_pdf_page": self.end_pdf_page,
            "page_count": self.end_pdf_page - self.start_pdf_page + 1,
            "section_count": len(self.sections),
            "sections": [
                {"title": item.title, "pdf_page": item.pdf_page, "depth": item.depth}
                for item in self.sections
            ],
        }


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def flatten_outline(reader: PdfReader, items: Iterable[Any], depth: int = 0) -> list[Bookmark]:
    flattened: list[Bookmark] = []
    for item in items:
        if isinstance(item, list):
            flattened.extend(flatten_outline(reader, item, depth + 1))
            continue
        try:
            page = reader.get_destination_page_number(item) + 1
        except Exception:
            continue
        flattened.append(
            Bookmark(
                title=str(getattr(item, "title", item)).strip(),
                pdf_page=page,
                depth=depth,
            )
        )
    return flattened


def identify_chapters(reader: PdfReader) -> list[Chapter]:
    bookmarks = flatten_outline(reader, reader.outline)
    chapter_bookmarks: list[tuple[int, Bookmark]] = []
    for index, bookmark in enumerate(bookmarks):
        match = CHAPTER_RE.match(bookmark.title)
        if bookmark.depth == 0 and match:
            chapter_bookmarks.append((index, bookmark))

    numbers = [
        int(CHAPTER_RE.match(bookmark.title).group(1))
        for _, bookmark in chapter_bookmarks
    ]
    if numbers != list(range(1, 86)):
        raise ValueError(f"Expected chapters 1-85, found: {numbers}")

    chapters: list[Chapter] = []
    for position, (bookmark_index, bookmark) in enumerate(chapter_bookmarks):
        match = CHAPTER_RE.match(bookmark.title)
        number = int(match.group(1))
        next_page = (
            chapter_bookmarks[position + 1][1].pdf_page
            if position + 1 < len(chapter_bookmarks)
            else len(reader.pages) + 1
        )
        next_index = (
            chapter_bookmarks[position + 1][0]
            if position + 1 < len(chapter_bookmarks)
            else len(bookmarks)
        )
        sections = [
            item
            for item in bookmarks[bookmark_index + 1 : next_index]
            if item.depth > 0 and bookmark.pdf_page <= item.pdf_page < next_page
        ]
        chapters.append(
            Chapter(
                number=number,
                chapter_id=f"CH{number:03d}",
                title=match.group(2).strip(),
                start_pdf_page=bookmark.pdf_page,
                end_pdf_page=next_page - 1,
                sections=sections,
            )
        )
    return chapters


def extract_page_text(reader: PdfReader, pdf_page: int) -> str:
    page = reader.pages[pdf_page - 1]
    try:
        text = page.extract_text(extraction_mode="layout")
    except TypeError:
        text = page.extract_text()
    return (text or "").replace("\r\n", "\n").replace("\r", "\n").strip()


def extract_chapter(
    reader: PdfReader,
    chapter: Chapter,
    output_dir: Path,
    source_pdf: Path,
    source_pdf_sha256: str,
    overwrite: bool,
) -> tuple[Path, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    text_path = output_dir / f"chapter_{chapter.number:03d}.txt"
    manifest_path = output_dir / f"chapter_{chapter.number:03d}_manifest.json"
    if text_path.exists() and manifest_path.exists() and not overwrite:
        return text_path, manifest_path

    pages: list[str] = []
    page_records: list[dict[str, Any]] = []
    character_offset = 0
    for pdf_page in range(chapter.start_pdf_page, chapter.end_pdf_page + 1):
        text = extract_page_text(reader, pdf_page)
        start_offset = character_offset
        pages.append(text)
        character_offset += len(text)
        page_records.append(
            {
                "pdf_page": pdf_page,
                "start_character_offset": start_offset,
                "end_character_offset": character_offset,
                "extracted_character_count": len(text),
            }
        )
        character_offset += 1

    text_path.write_text("\f".join(pages), encoding="utf-8")
    manifest = {
        **chapter.to_catalog_entry(),
        "source_pdf_name": source_pdf.name,
        "source_pdf_sha256": source_pdf_sha256,
        "text_file": text_path.name,
        "text_sha256": file_sha256(text_path),
        "extraction_method": "pypdf bookmark-guided page extraction",
        "page_separator": "form_feed",
        "pages": page_records,
    }
    manifest_path.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return text_path, manifest_path


def write_catalog(
    path: Path,
    source_pdf: Path,
    source_pdf_sha256: str,
    reader: PdfReader,
    chapters: list[Chapter],
) -> None:
    payload = {
        "source_pdf_name": source_pdf.name,
        "source_pdf_sha256": source_pdf_sha256,
        "pdf_page_count": len(reader.pages),
        "chapter_count": len(chapters),
        "chapters": [chapter.to_catalog_entry() for chapter in chapters],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Identify and extract all 85 Brenner chapters from PDF bookmarks."
    )
    parser.add_argument("--pdf", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, default=Path("data/raw_chapters"))
    parser.add_argument("--catalog", type=Path, default=Path("data/chapter_catalog.json"))
    parser.add_argument("--start-chapter", type=int, default=1)
    parser.add_argument("--end-chapter", type=int, default=85)
    parser.add_argument("--catalog-only", action="store_true")
    parser.add_argument("--overwrite", action="store_true")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not args.pdf.exists():
        raise SystemExit(f"PDF not found: {args.pdf}")
    if not 1 <= args.start_chapter <= args.end_chapter <= 85:
        raise SystemExit("Chapter range must satisfy 1 <= start <= end <= 85.")

    reader = PdfReader(args.pdf)
    chapters = identify_chapters(reader)
    source_hash = file_sha256(args.pdf)
    write_catalog(args.catalog, args.pdf, source_hash, reader, chapters)
    print(f"identified {len(chapters)} chapters -> {args.catalog}", flush=True)
    if args.catalog_only:
        return

    for chapter in chapters:
        if not args.start_chapter <= chapter.number <= args.end_chapter:
            continue
        text_path, manifest_path = extract_chapter(
            reader,
            chapter,
            args.output_dir,
            args.pdf,
            source_hash,
            args.overwrite,
        )
        print(
            f"{chapter.chapter_id}: pages {chapter.start_pdf_page}-{chapter.end_pdf_page} "
            f"-> {text_path.name}, {manifest_path.name}",
            flush=True,
        )


if __name__ == "__main__":
    main()
