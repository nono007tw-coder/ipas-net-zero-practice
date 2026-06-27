from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from blueprint import validate_blueprint
from chunking import chunk_paragraphs
from deduplicate import deduplicate
from generate_questions import batch_range, validate_generated
from schemas import QuestionItem
from select_exam import select_questions, write_answer_key, write_docx, write_exam_xlsx


def make_question(
    question_id: str,
    concept: str,
    stem: str,
    chapter_id: str = "CH001",
    score: int = 95,
    status: str = "accepted",
) -> QuestionItem:
    return QuestionItem(
        question_id=question_id,
        chapter_id=chapter_id,
        chapter_title="Test chapter",
        section_title="Test section",
        source_chunk_id=f"{chapter_id}-S01-C001",
        source_paragraph_range="P0001-P0002",
        tested_concept=concept,
        question_type="mechanism",
        difficulty="basic",
        stem=stem,
        options={
            "A": "Option A",
            "B": "Option B",
            "C": "Option C",
            "D": "Option D",
            "E": "Option E",
        },
        correct_answer="A",
        explanation="Source-based explanation.",
        option_explanations={
            "A": "Correct.",
            "B": "Incorrect.",
            "C": "Incorrect.",
            "D": "Incorrect.",
            "E": "Incorrect.",
        },
        source_basis="Brief source summary.",
        quality_score=score,
        review_status=status,
    )


class PipelineTests(unittest.TestCase):
    def test_chunking_assigns_traceable_ids(self) -> None:
        paragraphs = ["Renal Physiology"] + [
            "This paragraph contains enough source words for a deterministic chunk test."
            for _ in range(12)
        ]
        chunks = chunk_paragraphs(
            paragraphs,
            chapter_id="CH001",
            chapter_title="Test chapter",
            min_words=20,
            max_words=80,
        )
        self.assertGreaterEqual(len(chunks), 2)
        self.assertEqual(chunks[0].chunk_id, "CH001-S01-C001")
        self.assertTrue(chunks[0].paragraph_range.startswith("P"))

    def test_blueprint_requires_exact_100_question_plan(self) -> None:
        distribution = {
            "definition": 15,
            "mechanism": 30,
            "pathophysiology": 20,
            "comparison": 10,
            "clinical_significance": 10,
            "classification": 10,
            "figure_table_understanding": 5,
        }
        payload = {
            "chapter_id": "CH001",
            "chapter_title": "Test",
            "sections": [{"section_title": "A"}],
            "question_distribution": distribution,
            "difficulty_distribution": {"basic": 80, "basic_to_intermediate": 20},
            "question_plan": [
                {"question_id": f"CH001-Q{index:03d}"} for index in range(1, 101)
            ],
        }
        self.assertEqual(validate_blueprint(payload, "CH001"), [])

    def test_generation_batch_requires_ten_expected_ids(self) -> None:
        chunk = {
            "chapter_id": "CH001",
            "chapter_title": "Test chapter",
            "section_title": "Test section",
            "chunk_id": "CH001-S01-C001",
            "paragraph_range": "P0001-P0002",
        }
        records = []
        for index in range(1, 11):
            item = make_question(
                f"CH001-Q{index:03d}",
                f"Concept {index}",
                f"Question stem {index}?",
                status="draft",
                score=0,
            ).to_dict()
            item["source_chunk_id"] = chunk["chunk_id"]
            records.append(item)
        validated = validate_generated(records, "CH001", 1, {chunk["chunk_id"]: chunk})
        self.assertEqual(len(validated), 10)
        self.assertEqual(batch_range("CH001", 1)[2], "CH001-Q001 to CH001-Q010")

    def test_deduplication_keeps_higher_quality_item(self) -> None:
        high = make_question("CH001-Q001", "GFR regulation", "Which statement describes GFR regulation?", score=96)
        low = make_question("CH001-Q002", "GFR regulation", "Which statement describes GFR regulation?", score=91)
        retained, matches = deduplicate([low, high], threshold=0.86)
        self.assertEqual([item.question_id for item in retained], ["CH001-Q001"])
        self.assertEqual(matches[0].duplicate_question_id, "CH001-Q002")

    def test_exam_selection_respects_requested_count(self) -> None:
        pool = [
            make_question(
                question_id=f"CH{((index - 1) % 2) + 1:03d}-Q{index:03d}",
                chapter_id=f"CH{((index - 1) % 2) + 1:03d}",
                concept=f"Concept {index}",
                stem=f"Unique stem {index}?",
            )
            for index in range(1, 21)
        ]
        selected = select_questions(pool, 10, {"CH001": 5, "CH002": 1}, seed=7)
        self.assertEqual(len(selected), 10)
        self.assertGreater(
            sum(item.chapter_id == "CH001" for item in selected),
            sum(item.chapter_id == "CH002" for item in selected),
        )

    def test_question_json_round_trip(self) -> None:
        item = make_question("CH001-Q001", "Concept", "Stem?")
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "item.json"
            path.write_text(json.dumps(item.to_dict()), encoding="utf-8")
            loaded = QuestionItem.from_dict(json.loads(path.read_text(encoding="utf-8")))
        self.assertEqual(loaded.validate(), [])
        self.assertEqual(loaded.question_id, item.question_id)

    def test_exam_files_are_created(self) -> None:
        items = [
            make_question(f"CH001-Q{index:03d}", f"Concept {index}", f"Stem {index}?")
            for index in range(1, 4)
        ]
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            exam_path = root / "exam.xlsx"
            key_path = root / "answer_key.xlsx"
            questions_path = root / "questions.docx"
            explanations_path = root / "explanations.docx"
            write_exam_xlsx(exam_path, items)
            write_answer_key(key_path, items)
            write_docx(questions_path, items, False)
            write_docx(explanations_path, items, True)
            for path in (exam_path, key_path, questions_path, explanations_path):
                self.assertTrue(path.exists())
                self.assertGreater(path.stat().st_size, 0)


if __name__ == "__main__":
    unittest.main()
