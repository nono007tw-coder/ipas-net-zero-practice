from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Iterable

from schemas import ChunkItem


DEFAULT_MIN_WORDS = 500
DEFAULT_MAX_WORDS = 1200


SECTION_HEADING_RE = re.compile(
    r"^([A-Z][A-Za-z0-9 ,;:'’()/ \-]+|[0-9]+(?:\.[0-9]+)*\s+.+)$"
)


def read_text(path: Path) -> str:
    if not path.exists():
        raise FileNotFoundError(f"Input file not found: {path}")
    return path.read_text(encoding="utf-8-sig")


def word_count(text: str) -> int:
    return len(re.findall(r"\b\S+\b", text))


def split_paragraphs(text: str) -> list[str]:
    normalized = text.replace("\r\n", "\n").replace("\r", "\n")
    raw_paragraphs = re.split(r"\n\s*\n+", normalized)
    return [paragraph.strip() for paragraph in raw_paragraphs if paragraph.strip()]


def looks_like_section_title(paragraph: str) -> bool:
    stripped = " ".join(paragraph.split())
    if not stripped or len(stripped) > 120:
        return False
    if stripped.endswith("."):
        return False
    return bool(SECTION_HEADING_RE.match(stripped))


def infer_chapter_id(path: Path) -> str:
    match = re.search(r"chapter[_\- ]?(\d{1,3})", path.stem, re.IGNORECASE)
    if not match:
        return "CH000"
    return f"CH{int(match.group(1)):03d}"


def infer_chapter_title(path: Path, paragraphs: list[str]) -> str:
    for paragraph in paragraphs[:5]:
        title = " ".join(paragraph.split())
        if 4 <= len(title) <= 160:
            return title
    return path.stem.replace("_", " ").title()


def chunk_paragraphs(
    paragraphs: list[str],
    chapter_id: str,
    chapter_title: str,
    min_words: int = DEFAULT_MIN_WORDS,
    max_words: int = DEFAULT_MAX_WORDS,
) -> list[ChunkItem]:
    chunks: list[ChunkItem] = []
    current: list[tuple[int, str]] = []
    current_section = "Unspecified section"
    section_index = 0
    chunk_index_by_section: dict[int, int] = {}

    def flush() -> None:
        nonlocal current
        if not current:
            return
        start_para = current[0][0]
        end_para = current[-1][0]
        text = "\n\n".join(paragraph for _, paragraph in current)
        count = word_count(text)
        if count == 0:
            current = []
            return
        chunk_index_by_section[section_index] = chunk_index_by_section.get(section_index, 0) + 1
        chunk_number = chunk_index_by_section[section_index]
        chunks.append(
            ChunkItem(
                chapter_id=chapter_id,
                chapter_title=chapter_title,
                section_title=current_section,
                chunk_id=f"{chapter_id}-S{section_index:02d}-C{chunk_number:03d}",
                paragraph_range=f"P{start_para:04d}-P{end_para:04d}",
                text=text,
                word_count=count,
            )
        )
        current = []

    for paragraph_number, paragraph in enumerate(paragraphs, start=1):
        if looks_like_section_title(paragraph):
            if current and word_count("\n\n".join(text for _, text in current)) >= min_words:
                flush()
            section_index += 1
            current_section = " ".join(paragraph.split())
            continue

        candidate_words = word_count("\n\n".join([*(text for _, text in current), paragraph]))
        if current and candidate_words > max_words:
            flush()
        current.append((paragraph_number, paragraph))

    flush()

    if not chunks and paragraphs:
        text = "\n\n".join(paragraphs)
        chunks.append(
            ChunkItem(
                chapter_id=chapter_id,
                chapter_title=chapter_title,
                section_title="Unspecified section",
                chunk_id=f"{chapter_id}-S00-C001",
                paragraph_range=f"P0001-P{len(paragraphs):04d}",
                text=text,
                word_count=word_count(text),
            )
        )
    return chunks


def write_chunks(chunks: Iterable[ChunkItem], output: Path) -> None:
    output.parent.mkdir(parents=True, exist_ok=True)
    payload = [chunk.to_dict() for chunk in chunks]
    output.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def chunk_file(
    input_path: Path,
    output_path: Path,
    chapter_id: str | None = None,
    chapter_title: str | None = None,
    min_words: int = DEFAULT_MIN_WORDS,
    max_words: int = DEFAULT_MAX_WORDS,
) -> list[ChunkItem]:
    text = read_text(input_path)
    paragraphs = split_paragraphs(text)
    resolved_chapter_id = chapter_id or infer_chapter_id(input_path)
    resolved_chapter_title = chapter_title or infer_chapter_title(input_path, paragraphs)
    chunks = chunk_paragraphs(
        paragraphs=paragraphs,
        chapter_id=resolved_chapter_id,
        chapter_title=resolved_chapter_title,
        min_words=min_words,
        max_words=max_words,
    )
    errors = [error for chunk in chunks for error in chunk.validate()]
    if errors:
        raise ValueError("; ".join(errors))
    write_chunks(chunks, output_path)
    return chunks


def chunk_directory(input_dir: Path, output_dir: Path, min_words: int, max_words: int) -> None:
    if not input_dir.exists():
        raise FileNotFoundError(f"Input directory not found: {input_dir}")
    files = sorted(input_dir.glob("chapter_*.txt"))
    if not files:
        raise FileNotFoundError(f"No chapter_*.txt files found in: {input_dir}")
    for input_path in files:
        chapter_id = infer_chapter_id(input_path)
        output_path = output_dir / f"{input_path.stem}_chunks.json"
        chunks = chunk_file(
            input_path=input_path,
            output_path=output_path,
            chapter_id=chapter_id,
            chapter_title=None,
            min_words=min_words,
            max_words=max_words,
        )
        print(f"{input_path.name}: {len(chunks)} chunks -> {output_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Split Brenner chapter text into traceable chunks.")
    parser.add_argument("--input", type=Path, help="Input chapter txt file.")
    parser.add_argument("--output", type=Path, help="Output chunk JSON file.")
    parser.add_argument("--input-dir", type=Path, help="Directory containing chapter_001.txt ... chapter_085.txt.")
    parser.add_argument("--output-dir", type=Path, help="Directory for generated chunk JSON files.")
    parser.add_argument("--chapter-id", help="Chapter ID, for example CH001.")
    parser.add_argument("--chapter-title", help="Chapter title.")
    parser.add_argument("--min-words", type=int, default=DEFAULT_MIN_WORDS)
    parser.add_argument("--max-words", type=int, default=DEFAULT_MAX_WORDS)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.input_dir or args.output_dir:
        if not args.input_dir or not args.output_dir:
            raise SystemExit("--input-dir and --output-dir must be provided together.")
        chunk_directory(args.input_dir, args.output_dir, args.min_words, args.max_words)
        return

    if not args.input or not args.output:
        raise SystemExit("--input and --output are required for single-file chunking.")

    chunks = chunk_file(
        input_path=args.input,
        output_path=args.output,
        chapter_id=args.chapter_id,
        chapter_title=args.chapter_title,
        min_words=args.min_words,
        max_words=args.max_words,
    )
    print(f"{args.input.name}: {len(chunks)} chunks -> {args.output}")


if __name__ == "__main__":
    main()
