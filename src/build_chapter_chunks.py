from __future__ import annotations

import argparse
import json
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from schemas import ChunkItem
from utils import write_json


EXCLUDED_SECTION_TERMS = (
    "acknowledgment",
    "acknowledgement",
    "references",
    "board review questions",
)


@dataclass(slots=True)
class Paragraph:
    number: int
    pdf_page: int
    text: str
    word_count: int


def count_words(text: str) -> int:
    return len(re.findall(r"\b\S+\b", text))


def split_page_paragraphs(page_text: str, page: int, start_number: int) -> list[Paragraph]:
    raw = re.split(r"\n\s*\n+", page_text.replace("\r\n", "\n").replace("\r", "\n"))
    paragraphs: list[Paragraph] = []
    number = start_number
    for value in raw:
        text = value.strip()
        if not text:
            continue
        paragraphs.append(
            Paragraph(
                number=number,
                pdf_page=page,
                text=text,
                word_count=count_words(text),
            )
        )
        number += 1
    return paragraphs


def is_excluded(title: str) -> bool:
    normalized = title.casefold()
    return any(term in normalized for term in EXCLUDED_SECTION_TERMS)


def select_section_boundaries(
    chapter: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], int]:
    start = int(chapter["start_pdf_page"])
    end = int(chapter["end_pdf_page"])
    excluded: list[str] = []
    excluded_pages: list[int] = []
    candidates: list[dict[str, Any]] = []
    for section in chapter.get("sections", []):
        title = str(section.get("title", "")).strip()
        page = int(section.get("pdf_page", start))
        depth = int(section.get("depth", 1))
        if not title or not start <= page <= end:
            continue
        if is_excluded(title) or title.casefold() == "chapter outline":
            excluded.append(title)
            if is_excluded(title):
                excluded_pages.append(page)
            continue
        if depth == 1:
            candidates.append({"title": title, "pdf_page": page})

    by_page: dict[int, dict[str, Any]] = {}
    for item in candidates:
        by_page[item["pdf_page"]] = item
    boundaries = [by_page[page] for page in sorted(by_page)]
    if not boundaries or boundaries[0]["pdf_page"] > start:
        boundaries.insert(0, {"title": str(chapter["chapter_title"]), "pdf_page": start})
    content_end = min(excluded_pages) - 1 if excluded_pages else end
    return boundaries, sorted(set(excluded)), content_end


def build_paragraphs(pages: list[str], first_pdf_page: int) -> list[Paragraph]:
    paragraphs: list[Paragraph] = []
    next_number = 1
    for offset, page_text in enumerate(pages):
        values = split_page_paragraphs(page_text, first_pdf_page + offset, next_number)
        paragraphs.extend(values)
        next_number += len(values)
    return paragraphs


def chunk_section(
    chapter_id: str,
    chapter_title: str,
    section_title: str,
    section_index: int,
    paragraphs: list[Paragraph],
    min_words: int,
    max_words: int,
) -> list[ChunkItem]:
    chunks: list[ChunkItem] = []
    current: list[Paragraph] = []
    current_words = 0

    def flush() -> None:
        nonlocal current, current_words
        if not current:
            return
        if (
            current_words < min_words
            and chunks
            and chunks[-1].word_count + current_words <= max_words
        ):
            previous = chunks[-1]
            previous.text = f"{previous.text}\n\n" + "\n\n".join(
                item.text for item in current
            )
            previous.word_count += current_words
            previous.paragraph_range = (
                previous.paragraph_range.split("-")[0]
                + f"-P{current[-1].number:04d}"
            )
            previous.source_pdf_page_range = (
                previous.source_pdf_page_range.split("-")[0]
                + f"-PDF{current[-1].pdf_page:04d}"
            )
            current = []
            current_words = 0
            return
        chunks.append(
            ChunkItem(
                chapter_id=chapter_id,
                chapter_title=chapter_title,
                section_title=section_title,
                chunk_id=f"{chapter_id}-S{section_index:02d}-C{len(chunks) + 1:03d}",
                paragraph_range=f"P{current[0].number:04d}-P{current[-1].number:04d}",
                text="\n\n".join(item.text for item in current),
                word_count=current_words,
                source_pdf_page_range=(
                    f"PDF{current[0].pdf_page:04d}-PDF{current[-1].pdf_page:04d}"
                ),
            )
        )
        current = []
        current_words = 0

    for paragraph in paragraphs:
        if current and current_words + paragraph.word_count > max_words:
            flush()
        current.append(paragraph)
        current_words += paragraph.word_count
        if current_words >= min_words and current_words >= max_words * 0.8:
            flush()
    flush()
    return chunks


def build_chapter_chunks(
    chapter: dict[str, Any],
    raw_text_path: Path,
    min_words: int,
    max_words: int,
) -> tuple[list[ChunkItem], list[str]]:
    pages = raw_text_path.read_text(encoding="utf-8").split("\f")
    expected_pages = int(chapter["page_count"])
    if len(pages) != expected_pages:
        raise ValueError(
            f"{chapter['chapter_id']}: expected {expected_pages} pages, found {len(pages)}"
        )
    paragraphs = build_paragraphs(pages, int(chapter["start_pdf_page"]))
    boundaries, excluded, content_end = select_section_boundaries(chapter)
    chunks: list[ChunkItem] = []
    boundaries = [
        boundary for boundary in boundaries if int(boundary["pdf_page"]) <= content_end
    ]

    for index, boundary in enumerate(boundaries, start=1):
        section_start = int(boundary["pdf_page"])
        section_end = (
            int(boundaries[index]["pdf_page"]) - 1
            if index < len(boundaries)
            else content_end
        )
        section_paragraphs = [
            paragraph
            for paragraph in paragraphs
            if section_start <= paragraph.pdf_page <= section_end
        ]
        chunks.extend(
            chunk_section(
                chapter_id=str(chapter["chapter_id"]),
                chapter_title=str(chapter["chapter_title"]),
                section_title=str(boundary["title"]),
                section_index=index,
                paragraphs=section_paragraphs,
                min_words=min_words,
                max_words=max_words,
            )
        )
    return chunks, excluded


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build page-traceable chunks for extracted chapters.")
    parser.add_argument("--catalog", type=Path, default=Path("data/chapter_catalog.json"))
    parser.add_argument("--raw-dir", type=Path, default=Path("data/raw_chapters"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/chunks"))
    parser.add_argument("--start-chapter", type=int, default=1)
    parser.add_argument("--end-chapter", type=int, default=85)
    parser.add_argument("--min-words", type=int, default=500)
    parser.add_argument("--max-words", type=int, default=1200)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 1 <= args.start_chapter <= args.end_chapter <= 85:
        raise SystemExit("Chapter range must satisfy 1 <= start <= end <= 85.")
    if not 1 <= args.min_words <= args.max_words:
        raise SystemExit("Word limits must satisfy 1 <= min_words <= max_words.")
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    for chapter in catalog["chapters"]:
        number = int(chapter["chapter_number"])
        if not args.start_chapter <= number <= args.end_chapter:
            continue
        chunks, excluded = build_chapter_chunks(
            chapter=chapter,
            raw_text_path=args.raw_dir / f"chapter_{number:03d}.txt",
            min_words=args.min_words,
            max_words=args.max_words,
        )
        errors = [error for chunk in chunks for error in chunk.validate()]
        if errors:
            raise ValueError(f"{chapter['chapter_id']}: {'; '.join(errors)}")
        write_json(
            args.output_dir / f"chapter_{number:03d}_chunks.json",
            [chunk.to_dict() for chunk in chunks],
        )
        write_json(
            args.output_dir / f"chapter_{number:03d}_chunks_meta.json",
            {
                "chapter_id": chapter["chapter_id"],
                "chapter_title": chapter["chapter_title"],
                "chunk_count": len(chunks),
                "total_words": sum(chunk.word_count for chunk in chunks),
                "excluded_content": excluded,
            },
        )
        print(
            f"{chapter['chapter_id']}: {len(chunks)} chunks, "
            f"{sum(chunk.word_count for chunk in chunks):,} words",
            flush=True,
        )


if __name__ == "__main__":
    main()
