from __future__ import annotations

import argparse
import json
from collections import defaultdict
from pathlib import Path
from typing import Any

from blueprint import validate_blueprint
from utils import write_json


QUESTION_TYPE_COUNTS = {
    "definition": 15,
    "mechanism": 30,
    "pathophysiology": 20,
    "comparison": 10,
    "clinical_significance": 10,
    "classification": 10,
    "figure_table_understanding": 5,
}
DIFFICULTY_COUNTS = {"basic": 80, "basic_to_intermediate": 20}


def allocate_counts(weights: list[int], total: int) -> list[int]:
    if not weights:
        return []
    weight_total = sum(weights)
    raw = [total * weight / weight_total for weight in weights]
    counts = [max(1, int(value)) for value in raw]
    while sum(counts) > total:
        candidates = [index for index, count in enumerate(counts) if count > 1]
        index = min(candidates, key=lambda item: raw[item] - counts[item])
        counts[index] -= 1
    while sum(counts) < total:
        index = max(range(len(counts)), key=lambda item: raw[item] - counts[item])
        counts[index] += 1
    return counts


def expanded_distribution(distribution: dict[str, int]) -> list[str]:
    values: list[str] = []
    for name, count in distribution.items():
        values.extend([name] * count)
    return values


def build_blueprint(
    chapter: dict[str, Any],
    chunks: list[dict[str, Any]],
    clinical_weight: int,
) -> dict[str, Any]:
    section_chunks: dict[str, list[dict[str, Any]]] = defaultdict(list)
    section_order: list[str] = []
    for chunk in chunks:
        section = str(chunk["section_title"])
        if section not in section_chunks:
            section_order.append(section)
        section_chunks[section].append(chunk)

    weights = [
        sum(int(item["word_count"]) for item in section_chunks[name])
        for name in section_order
    ]
    section_counts = allocate_counts(weights, 100)
    sections: list[dict[str, Any]] = []
    for title, count in zip(section_order, section_counts):
        all_chunk_ids = [item["chunk_id"] for item in section_chunks[title]]
        eligible_chunk_ids = [
            item["chunk_id"]
            for item in section_chunks[title]
            if int(item["word_count"]) >= 300
        ] or all_chunk_ids
        sections.append(
            {
                "section_title": title,
                "chunk_ids": all_chunk_ids,
                "eligible_source_chunk_ids": eligible_chunk_ids,
                "key_concepts": [title],
                "recommended_question_count": count,
                "preferred_question_types": [
                    "mechanism",
                    "pathophysiology",
                    "clinical_significance",
                ],
            }
        )

    question_types = expanded_distribution(QUESTION_TYPE_COUNTS)
    difficulties = expanded_distribution(DIFFICULTY_COUNTS)
    plan: list[dict[str, Any]] = []
    question_number = 1
    for section, count in zip(sections, section_counts):
        chunk_ids = section["eligible_source_chunk_ids"]
        for local_index in range(count):
            plan.append(
                {
                    "question_id": f"{chapter['chapter_id']}-Q{question_number:03d}",
                    "source_chunk_ids": [chunk_ids[local_index % len(chunk_ids)]],
                    "tested_concept": section["section_title"],
                    "question_type": question_types[question_number - 1],
                    "difficulty": difficulties[question_number - 1],
                }
            )
            question_number += 1

    core_themes = [
        item["section_title"]
        for item in sorted(
            sections,
            key=lambda value: value["recommended_question_count"],
            reverse=True,
        )[: min(8, len(sections))]
    ]
    return {
        "chapter_id": chapter["chapter_id"],
        "chapter_title": chapter["chapter_title"],
        "clinical_weight": clinical_weight,
        "core_themes": core_themes,
        "sections": sections,
        "question_distribution": QUESTION_TYPE_COUNTS,
        "difficulty_distribution": DIFFICULTY_COUNTS,
        "question_plan": plan,
        "unsuitable_content": [
            "References",
            "Acknowledgments",
            "Existing Board Review Questions",
        ],
        "generation_note": (
            "Automatically allocated from user-provided Brenner chunks. "
            "Each question must still be generated and reviewed against its source chunk."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Build deterministic 100-question blueprints for extracted chapters."
    )
    parser.add_argument("--catalog", type=Path, default=Path("data/chapter_catalog.json"))
    parser.add_argument("--chunks-dir", type=Path, default=Path("data/chunks"))
    parser.add_argument("--output-dir", type=Path, default=Path("data/blueprints"))
    parser.add_argument(
        "--weights",
        type=Path,
        default=Path("data/blueprints/chapter_weights.json"),
    )
    parser.add_argument("--start-chapter", type=int, default=1)
    parser.add_argument("--end-chapter", type=int, default=85)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    catalog = json.loads(args.catalog.read_text(encoding="utf-8"))
    chapter_weights = json.loads(args.weights.read_text(encoding="utf-8"))
    summaries: list[dict[str, Any]] = []
    for chapter in catalog["chapters"]:
        number = int(chapter["chapter_number"])
        if not args.start_chapter <= number <= args.end_chapter:
            continue
        chunks = json.loads(
            (args.chunks_dir / f"chapter_{number:03d}_chunks.json").read_text(
                encoding="utf-8"
            )
        )
        if not chunks:
            raise ValueError(f"{chapter['chapter_id']}: no chunks found")
        clinical_weight = int(chapter_weights.get(str(chapter["chapter_id"]), 1))
        blueprint = build_blueprint(chapter, chunks, clinical_weight)
        errors = validate_blueprint(blueprint, str(chapter["chapter_id"]))
        if errors:
            raise ValueError(f"{chapter['chapter_id']}: {'; '.join(errors)}")
        output = args.output_dir / f"{chapter['chapter_id']}_blueprint.json"
        write_json(output, blueprint)
        summaries.append(
            {
                "chapter_id": chapter["chapter_id"],
                "chapter_title": chapter["chapter_title"],
                "clinical_weight": clinical_weight,
                "section_count": len(blueprint["sections"]),
                "chunk_count": len(chunks),
                "total_words": sum(int(item["word_count"]) for item in chunks),
                "planned_questions": len(blueprint["question_plan"]),
            }
        )
        print(
            f"{chapter['chapter_id']}: 100-question blueprint, "
            f"{len(blueprint['sections'])} sections",
            flush=True,
        )
    write_json(
        args.output_dir / "blueprint_summary.json",
        {
            "chapter_count": len(summaries),
            "total_chunks": sum(item["chunk_count"] for item in summaries),
            "total_words": sum(item["total_words"] for item in summaries),
            "total_planned_questions": sum(
                item["planned_questions"] for item in summaries
            ),
            "chapters": summaries,
        },
    )


if __name__ == "__main__":
    main()
