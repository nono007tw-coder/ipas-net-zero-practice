from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from utils import chapter_number, read_json, render_template, write_json


QUESTION_TYPES = {
    "definition",
    "mechanism",
    "pathophysiology",
    "comparison",
    "clinical_significance",
    "classification",
    "figure_table_understanding",
}


def validate_blueprint(payload: dict[str, Any], chapter_id: str) -> list[str]:
    errors: list[str] = []
    if payload.get("chapter_id") != chapter_id:
        errors.append(f"chapter_id must be {chapter_id}")
    if not str(payload.get("chapter_title", "")).strip():
        errors.append("chapter_title is required")
    sections = payload.get("sections")
    if not isinstance(sections, list) or not sections:
        errors.append("sections must be a non-empty list")
    distribution = payload.get("question_distribution")
    if not isinstance(distribution, dict):
        errors.append("question_distribution must be an object")
    else:
        missing = QUESTION_TYPES - set(distribution)
        if missing:
            errors.append(f"missing question types: {', '.join(sorted(missing))}")
        unknown = set(distribution) - QUESTION_TYPES
        if unknown:
            errors.append(f"unknown question types: {', '.join(sorted(unknown))}")
        try:
            total = sum(int(value) for value in distribution.values())
            if total != 100:
                errors.append(f"question_distribution must total 100, got {total}")
        except (TypeError, ValueError):
            errors.append("question_distribution values must be integers")
    difficulty_distribution = payload.get("difficulty_distribution")
    if not isinstance(difficulty_distribution, dict):
        errors.append("difficulty_distribution must be an object")
    else:
        if set(difficulty_distribution) != {"basic", "basic_to_intermediate"}:
            errors.append("difficulty_distribution must contain basic and basic_to_intermediate")
        try:
            difficulty_total = sum(int(value) for value in difficulty_distribution.values())
            if difficulty_total != 100:
                errors.append(f"difficulty_distribution must total 100, got {difficulty_total}")
        except (TypeError, ValueError):
            errors.append("difficulty_distribution values must be integers")
    plan = payload.get("question_plan")
    if not isinstance(plan, list) or len(plan) != 100:
        errors.append("question_plan must contain exactly 100 entries")
    else:
        expected_ids = {f"{chapter_id}-Q{index:03d}" for index in range(1, 101)}
        actual_ids = {str(item.get("question_id", "")) for item in plan if isinstance(item, dict)}
        if actual_ids != expected_ids:
            errors.append("question_plan IDs must cover Q001-Q100 exactly")
    return errors


def build_prompt(chapter_id: str, chunks_path: Path, template_path: Path) -> str:
    chapter_number(chapter_id)
    chunks = read_json(chunks_path)
    if not isinstance(chunks, list) or not chunks:
        raise ValueError("Chapter chunks must be a non-empty JSON array")
    chunk_chapters = {str(chunk.get("chapter_id", "")) for chunk in chunks if isinstance(chunk, dict)}
    if chunk_chapters != {chapter_id}:
        raise ValueError(f"All chunks must belong to {chapter_id}; got {sorted(chunk_chapters)}")
    return render_template(
        template_path,
        {"chapter_chunks": json.dumps(chunks, ensure_ascii=False, indent=2)},
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare or validate a 100-question chapter blueprint.")
    parser.add_argument("--chapter", required=True, help="Chapter ID, for example CH001.")
    parser.add_argument("--chunks", type=Path, help="Chapter chunk JSON file.")
    parser.add_argument("--response", type=Path, help="Model-generated blueprint JSON to validate.")
    parser.add_argument("--output", type=Path, help="Output prompt or validated blueprint path.")
    parser.add_argument(
        "--template",
        type=Path,
        default=Path("prompts/01_chapter_blueprint_prompt.txt"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    chapter_number(args.chapter)
    if args.response:
        payload = read_json(args.response)
        if not isinstance(payload, dict):
            raise SystemExit("Blueprint response must be a JSON object.")
        errors = validate_blueprint(payload, args.chapter)
        if errors:
            raise SystemExit("Blueprint validation failed:\n- " + "\n- ".join(errors))
        output = args.output or Path("data/blueprints") / f"{args.chapter}_blueprint.json"
        write_json(output, payload)
        print(f"validated blueprint -> {output}")
        return

    chunks = args.chunks or Path("data/chunks") / f"chapter_{chapter_number(args.chapter):03d}_chunks.json"
    output = args.output or Path("data/blueprints") / f"{args.chapter}_blueprint_prompt.txt"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(build_prompt(args.chapter, chunks, args.template), encoding="utf-8")
    print(f"prepared blueprint prompt -> {output}")


if __name__ == "__main__":
    main()
