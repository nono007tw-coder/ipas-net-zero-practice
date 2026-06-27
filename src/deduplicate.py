from __future__ import annotations

import argparse
from dataclasses import dataclass
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from schemas import QuestionItem
from utils import load_records_from_directory, normalize_text, write_json


@dataclass(slots=True)
class DuplicateMatch:
    kept_question_id: str
    duplicate_question_id: str
    stem_similarity: float
    concept_similarity: float
    answer_similarity: float
    combined_similarity: float
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kept_question_id": self.kept_question_id,
            "duplicate_question_id": self.duplicate_question_id,
            "stem_similarity": round(self.stem_similarity, 4),
            "concept_similarity": round(self.concept_similarity, 4),
            "answer_similarity": round(self.answer_similarity, 4),
            "combined_similarity": round(self.combined_similarity, 4),
            "reason": self.reason,
        }


def similarity(left: str, right: str) -> float:
    return SequenceMatcher(None, normalize_text(left), normalize_text(right)).ratio()


def correct_answer_text(item: QuestionItem) -> str:
    return item.options.get(item.correct_answer, "")


def compare(left: QuestionItem, right: QuestionItem) -> tuple[float, float, float, float]:
    stem = similarity(left.stem, right.stem)
    concept = similarity(left.tested_concept, right.tested_concept)
    answer = similarity(correct_answer_text(left), correct_answer_text(right))
    combined = 0.5 * stem + 0.3 * concept + 0.2 * answer
    return stem, concept, answer, combined


def is_duplicate(
    left: QuestionItem,
    right: QuestionItem,
    combined: float,
    stem: float,
    concept: float,
    threshold: float,
) -> tuple[bool, str]:
    if left.question_id == right.question_id:
        return True, "same question_id"
    if normalize_text(left.stem) == normalize_text(right.stem):
        return True, "identical normalized stem"
    if stem >= 0.92:
        return True, "very high stem similarity"
    if concept >= 0.92 and combined >= threshold:
        return True, "same tested concept with similar item structure"
    return combined >= threshold, "combined semantic proxy similarity"


def deduplicate(items: list[QuestionItem], threshold: float) -> tuple[list[QuestionItem], list[DuplicateMatch]]:
    ranked = sorted(
        items,
        key=lambda item: (
            item.quality_score,
            item.review_status == "accepted",
            item.updated_at,
        ),
        reverse=True,
    )
    retained: list[QuestionItem] = []
    matches: list[DuplicateMatch] = []
    for candidate in ranked:
        duplicate_of: tuple[QuestionItem, float, float, float, float, str] | None = None
        for kept in retained:
            stem, concept, answer, combined = compare(candidate, kept)
            duplicate, reason = is_duplicate(candidate, kept, combined, stem, concept, threshold)
            if duplicate:
                duplicate_of = (kept, stem, concept, answer, combined, reason)
                break
        if duplicate_of:
            kept, stem, concept, answer, combined, reason = duplicate_of
            matches.append(
                DuplicateMatch(
                    kept_question_id=kept.question_id,
                    duplicate_question_id=candidate.question_id,
                    stem_similarity=stem,
                    concept_similarity=concept,
                    answer_similarity=answer,
                    combined_similarity=combined,
                    reason=reason,
                )
            )
        else:
            retained.append(candidate)
    retained.sort(key=lambda item: item.question_id)
    return retained, matches


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Detect and remove duplicate reviewed questions.")
    parser.add_argument("--input-dir", type=Path, default=Path("data/reviewed_questions"))
    parser.add_argument("--scope", choices=["chapter", "all"], default="chapter")
    parser.add_argument("--chapter", help="Required for chapter scope, for example CH001.")
    parser.add_argument("--threshold", type=float, default=0.86)
    parser.add_argument("--output-dir", type=Path, default=Path("data/final_item_bank"))
    parser.add_argument("--report", type=Path, default=Path("outputs/deduplication_report.json"))
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if not 0.0 < args.threshold <= 1.0:
        raise SystemExit("--threshold must be greater than 0 and no more than 1.")
    if args.scope == "chapter" and not args.chapter:
        raise SystemExit("--chapter is required when --scope chapter.")

    records = load_records_from_directory(args.input_dir)
    items: list[QuestionItem] = []
    for record in records:
        item = QuestionItem.from_dict(record)
        errors = item.validate()
        if errors:
            raise SystemExit(f"{item.question_id}: {'; '.join(errors)}")
        if args.scope == "chapter" and item.chapter_id != args.chapter:
            continue
        items.append(item)
    if not items:
        raise SystemExit("No matching reviewed questions found.")

    retained, matches = deduplicate(items, args.threshold)
    output_name = f"{args.chapter}_final.json" if args.scope == "chapter" else "all_chapters_final.json"
    output = args.output_dir / output_name
    write_json(output, [item.to_dict() for item in retained])
    write_json(
        args.report,
        {
            "scope": args.scope,
            "chapter": args.chapter,
            "threshold": args.threshold,
            "input_count": len(items),
            "retained_count": len(retained),
            "duplicate_count": len(matches),
            "matches": [match.to_dict() for match in matches],
        },
    )
    print(f"retained {len(retained)} of {len(items)} questions -> {output}")
    print(f"duplicate report -> {args.report}")


if __name__ == "__main__":
    main()
