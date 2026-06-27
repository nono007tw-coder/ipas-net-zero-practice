from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from schemas import QuestionItem
from utils import (
    chapter_number,
    compact_question_summary,
    ensure_unique,
    load_records,
    load_records_from_directory,
    read_json,
    render_template,
    write_json,
)


def batch_range(chapter_id: str, batch: int) -> tuple[int, int, str]:
    if not 1 <= batch <= 10:
        raise ValueError("batch must be from 1 to 10")
    start = (batch - 1) * 10 + 1
    end = start + 9
    return start, end, f"{chapter_id}-Q{start:03d} to {chapter_id}-Q{end:03d}"


def selected_chunks(blueprint: dict[str, Any], chunks: list[dict[str, Any]], batch: int) -> list[dict[str, Any]]:
    start, end, _ = batch_range(str(blueprint["chapter_id"]), batch)
    plan = blueprint.get("question_plan", [])[start - 1 : end]
    wanted = {
        str(chunk_id)
        for item in plan
        if isinstance(item, dict)
        for chunk_id in item.get("source_chunk_ids", [])
    }
    if not wanted:
        return chunks
    by_id = {str(chunk.get("chunk_id", "")): chunk for chunk in chunks}
    missing = wanted - set(by_id)
    if missing:
        raise ValueError(f"Blueprint references missing chunks: {', '.join(sorted(missing))}")
    return [by_id[chunk_id] for chunk_id in sorted(wanted)]


def validate_generated(
    records: list[dict[str, Any]],
    chapter_id: str,
    batch: int,
    chunk_by_id: dict[str, dict[str, Any]],
) -> list[QuestionItem]:
    start, end, _ = batch_range(chapter_id, batch)
    expected_ids = {f"{chapter_id}-Q{index:03d}" for index in range(start, end + 1)}
    actual_ids = {str(record.get("question_id", "")) for record in records}
    if actual_ids != expected_ids:
        raise ValueError(f"Response must contain exactly: {', '.join(sorted(expected_ids))}")
    ensure_unique(actual_ids, "question IDs")

    items: list[QuestionItem] = []
    errors: list[str] = []
    for record in records:
        chunk_id = str(record.get("source_chunk_id", ""))
        chunk = chunk_by_id.get(chunk_id)
        if not chunk:
            errors.append(f"{record.get('question_id')}: unknown source_chunk_id {chunk_id}")
            continue
        enriched = {
            **record,
            "chapter_id": chapter_id,
            "chapter_title": chunk.get("chapter_title", ""),
            "section_title": chunk.get("section_title", ""),
            "source_paragraph_range": chunk.get("paragraph_range", ""),
            "quality_score": 0,
            "review_status": "draft",
            "revision_notes": "",
        }
        item = QuestionItem.from_dict(enriched)
        item_errors = item.validate()
        if item_errors:
            errors.append(f"{item.question_id}: {'; '.join(item_errors)}")
        else:
            items.append(item)
    if errors:
        raise ValueError("Generated question validation failed:\n- " + "\n- ".join(errors))
    return items


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare or validate a 10-question generation batch.")
    parser.add_argument("--chapter", required=True)
    parser.add_argument("--batch", type=int, required=True)
    parser.add_argument("--blueprint", type=Path)
    parser.add_argument("--chunks", type=Path)
    parser.add_argument("--previous-dir", type=Path, default=Path("data/generated_questions"))
    parser.add_argument("--response", type=Path, help="Model response JSON array to validate.")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--template",
        type=Path,
        default=Path("prompts/02_question_generation_prompt.txt"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    number = chapter_number(args.chapter)
    batch_range(args.chapter, args.batch)
    blueprint_path = args.blueprint or Path("data/blueprints") / f"{args.chapter}_blueprint.json"
    chunks_path = args.chunks or Path("data/chunks") / f"chapter_{number:03d}_chunks.json"
    blueprint = read_json(blueprint_path)
    chunks = read_json(chunks_path)
    if not isinstance(blueprint, dict) or not isinstance(chunks, list):
        raise SystemExit("Blueprint must be an object and chunks must be an array.")
    chunk_by_id = {str(chunk.get("chunk_id", "")): chunk for chunk in chunks if isinstance(chunk, dict)}

    if args.response:
        records = load_records(args.response)
        items = validate_generated(records, args.chapter, args.batch, chunk_by_id)
        output = args.output or args.previous_dir / f"{args.chapter}_batch_{args.batch:02d}.json"
        write_json(output, [item.to_dict() for item in items])
        print(f"validated {len(items)} questions -> {output}")
        return

    previous = [
        item
        for item in load_records_from_directory(args.previous_dir)
        if str(item.get("chapter_id", "")).upper() == args.chapter
    ]
    _, _, question_id_range = batch_range(args.chapter, args.batch)
    prompt = render_template(
        args.template,
        {
            "chapter_blueprint": json.dumps(blueprint, ensure_ascii=False, indent=2),
            "previous_question_summary": json.dumps(
                compact_question_summary(previous), ensure_ascii=False, indent=2
            ),
            "question_id_range": question_id_range,
            "source_chunks": json.dumps(
                selected_chunks(blueprint, chunks, args.batch), ensure_ascii=False, indent=2
            ),
        },
    )
    output = args.output or args.previous_dir / f"{args.chapter}_batch_{args.batch:02d}_prompt.txt"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(prompt, encoding="utf-8")
    print(f"prepared generation prompt -> {output}")


if __name__ == "__main__":
    main()
