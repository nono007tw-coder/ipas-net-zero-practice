from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from schemas import QuestionItem, utc_now_iso
from utils import (
    compact_question_summary,
    load_records,
    load_records_from_directory,
    read_json,
    render_template,
    write_json,
)


VALID_REVIEW_STATUSES = {"accepted", "minor_revision", "major_revision", "rejected"}


def build_review_prompt(
    question: dict[str, Any],
    chunks: list[dict[str, Any]],
    existing: list[dict[str, Any]],
    template: Path,
) -> str:
    source_id = str(question.get("source_chunk_id", ""))
    source = [chunk for chunk in chunks if str(chunk.get("chunk_id", "")) == source_id]
    if len(source) != 1:
        raise ValueError(f"Source chunk {source_id} was not found exactly once")
    return render_template(
        template,
        {
            "source_chunks": json.dumps(source, ensure_ascii=False, indent=2),
            "question_item": json.dumps(question, ensure_ascii=False, indent=2),
            "existing_question_summary": json.dumps(
                compact_question_summary(existing), ensure_ascii=False, indent=2
            ),
        },
    )


def apply_review(question: dict[str, Any], review: dict[str, Any]) -> QuestionItem:
    status = str(review.get("review_status", ""))
    score = review.get("quality_score")
    if status not in VALID_REVIEW_STATUSES:
        raise ValueError(f"Invalid review_status: {status}")
    if not isinstance(score, int) or not 0 <= score <= 100:
        raise ValueError("quality_score must be an integer from 0 to 100")
    revised = review.get("revised_question")
    payload = {**question, **(revised if isinstance(revised, dict) else {})}
    payload.update(
        {
            "quality_score": score,
            "review_status": status,
            "revision_notes": str(review.get("revision_notes", "")),
            "updated_at": utc_now_iso(),
        }
    )
    item = QuestionItem.from_dict(payload)
    errors = item.validate()
    if errors:
        raise ValueError("; ".join(errors))
    return item


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Prepare review prompts or apply a reviewer response.")
    parser.add_argument("--questions", type=Path, required=True)
    parser.add_argument("--chunks", type=Path, required=True)
    parser.add_argument("--question-id", help="Prepare a prompt for one question.")
    parser.add_argument("--existing-dir", type=Path, default=Path("data/reviewed_questions"))
    parser.add_argument("--response", type=Path, help="Reviewer response JSON.")
    parser.add_argument("--output", type=Path)
    parser.add_argument(
        "--template",
        type=Path,
        default=Path("prompts/03_quality_review_prompt.txt"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    questions = load_records(args.questions)
    chunks = read_json(args.chunks)
    if not isinstance(chunks, list):
        raise SystemExit("Chunks must be a JSON array.")

    if args.response:
        reviews = load_records(args.response)
        review_by_id = {
            str(review.get("question_id", "")): review
            for review in reviews
            if isinstance(review, dict)
        }
        reviewed: list[QuestionItem] = []
        for question in questions:
            question_id = str(question.get("question_id", ""))
            review = review_by_id.get(question_id)
            if not review and len(questions) == 1 and len(reviews) == 1:
                review = reviews[0]
            if not review:
                raise SystemExit(f"Missing review for {question_id}")
            reviewed.append(apply_review(question, review))
        output = args.output or Path("data/reviewed_questions") / f"{args.questions.stem}_reviewed.json"
        write_json(output, [item.to_dict() for item in reviewed])
        print(f"applied {len(reviewed)} reviews -> {output}")
        return

    if not args.question_id:
        raise SystemExit("--question-id is required when preparing a review prompt.")
    matches = [question for question in questions if question.get("question_id") == args.question_id]
    if len(matches) != 1:
        raise SystemExit(f"Expected one question with ID {args.question_id}, found {len(matches)}")
    existing = load_records_from_directory(args.existing_dir)
    prompt = build_review_prompt(matches[0], chunks, existing, args.template)
    output = args.output or args.existing_dir / f"{args.question_id}_review_prompt.txt"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(prompt, encoding="utf-8")
    print(f"prepared review prompt -> {output}")


if __name__ == "__main__":
    main()
