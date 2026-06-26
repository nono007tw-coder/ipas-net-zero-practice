from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Literal


QuestionType = Literal[
    "definition",
    "mechanism",
    "pathophysiology",
    "comparison",
    "clinical_significance",
    "classification",
    "figure_table_understanding",
]

Difficulty = Literal["basic", "basic_to_intermediate"]
ReviewStatus = Literal["draft", "accepted", "minor_revision", "major_revision", "rejected"]
AnswerChoice = Literal["A", "B", "C", "D", "E"]


OPTION_KEYS: tuple[str, ...] = ("A", "B", "C", "D", "E")
QUESTION_TYPES: tuple[str, ...] = (
    "definition",
    "mechanism",
    "pathophysiology",
    "comparison",
    "clinical_significance",
    "classification",
    "figure_table_understanding",
)
DIFFICULTIES: tuple[str, ...] = ("basic", "basic_to_intermediate")
REVIEW_STATUSES: tuple[str, ...] = (
    "draft",
    "accepted",
    "minor_revision",
    "major_revision",
    "rejected",
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


@dataclass(slots=True)
class ChunkItem:
    chapter_id: str
    chapter_title: str
    section_title: str
    chunk_id: str
    paragraph_range: str
    text: str
    word_count: int

    def validate(self) -> list[str]:
        errors: list[str] = []
        for field_name in (
            "chapter_id",
            "chapter_title",
            "section_title",
            "chunk_id",
            "paragraph_range",
            "text",
        ):
            if not str(getattr(self, field_name)).strip():
                errors.append(f"{field_name} is required")
        if self.word_count <= 0:
            errors.append("word_count must be positive")
        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class QuestionItem:
    question_id: str
    chapter_id: str
    chapter_title: str
    section_title: str
    source_chunk_id: str
    source_paragraph_range: str
    tested_concept: str
    question_type: QuestionType
    difficulty: Difficulty
    stem: str
    options: dict[str, str]
    correct_answer: AnswerChoice
    explanation: str
    option_explanations: dict[str, str]
    source_basis: str
    quality_score: int = 0
    review_status: ReviewStatus = "draft"
    revision_notes: str = ""
    created_at: str = field(default_factory=utc_now_iso)
    updated_at: str = field(default_factory=utc_now_iso)

    def validate(self) -> list[str]:
        errors: list[str] = []
        required_text_fields = (
            "question_id",
            "chapter_id",
            "chapter_title",
            "section_title",
            "source_chunk_id",
            "source_paragraph_range",
            "tested_concept",
            "stem",
            "explanation",
            "source_basis",
        )
        for field_name in required_text_fields:
            if not str(getattr(self, field_name)).strip():
                errors.append(f"{field_name} is required")

        if self.question_type not in QUESTION_TYPES:
            errors.append(f"question_type must be one of: {', '.join(QUESTION_TYPES)}")
        if self.difficulty not in DIFFICULTIES:
            errors.append(f"difficulty must be one of: {', '.join(DIFFICULTIES)}")
        if self.review_status not in REVIEW_STATUSES:
            errors.append(f"review_status must be one of: {', '.join(REVIEW_STATUSES)}")
        if self.correct_answer not in OPTION_KEYS:
            errors.append("correct_answer must be A, B, C, D, or E")
        if not isinstance(self.quality_score, int) or not 0 <= self.quality_score <= 100:
            errors.append("quality_score must be an integer from 0 to 100")

        option_keys = set(self.options)
        explanation_keys = set(self.option_explanations)
        expected = set(OPTION_KEYS)
        if option_keys != expected:
            errors.append("options must contain exactly A, B, C, D, and E")
        if explanation_keys != expected:
            errors.append("option_explanations must contain exactly A, B, C, D, and E")
        for key in OPTION_KEYS:
            if not str(self.options.get(key, "")).strip():
                errors.append(f"option {key} is required")
            if not str(self.option_explanations.get(key, "")).strip():
                errors.append(f"option_explanations.{key} is required")

        return errors

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "QuestionItem":
        return cls(
            question_id=str(data.get("question_id", "")),
            chapter_id=str(data.get("chapter_id", "")),
            chapter_title=str(data.get("chapter_title", "")),
            section_title=str(data.get("section_title", "")),
            source_chunk_id=str(data.get("source_chunk_id", "")),
            source_paragraph_range=str(data.get("source_paragraph_range", "")),
            tested_concept=str(data.get("tested_concept", "")),
            question_type=data.get("question_type", "definition"),
            difficulty=data.get("difficulty", "basic"),
            stem=str(data.get("stem", "")),
            options=dict(data.get("options", {})),
            correct_answer=data.get("correct_answer", "A"),
            explanation=str(data.get("explanation", "")),
            option_explanations=dict(data.get("option_explanations", {})),
            source_basis=str(data.get("source_basis", "")),
            quality_score=int(data.get("quality_score", 0) or 0),
            review_status=data.get("review_status", "draft"),
            revision_notes=str(data.get("revision_notes", "")),
            created_at=str(data.get("created_at") or utc_now_iso()),
            updated_at=str(data.get("updated_at") or utc_now_iso()),
        )

    def to_export_row(self) -> dict[str, Any]:
        return {
            "question_id": self.question_id,
            "chapter_id": self.chapter_id,
            "chapter_title": self.chapter_title,
            "section_title": self.section_title,
            "source_chunk_id": self.source_chunk_id,
            "source_paragraph_range": self.source_paragraph_range,
            "tested_concept": self.tested_concept,
            "question_type": self.question_type,
            "difficulty": self.difficulty,
            "stem": self.stem,
            "option_a": self.options.get("A", ""),
            "option_b": self.options.get("B", ""),
            "option_c": self.options.get("C", ""),
            "option_d": self.options.get("D", ""),
            "option_e": self.options.get("E", ""),
            "correct_answer": self.correct_answer,
            "explanation": self.explanation,
            "option_a_explanation": self.option_explanations.get("A", ""),
            "option_b_explanation": self.option_explanations.get("B", ""),
            "option_c_explanation": self.option_explanations.get("C", ""),
            "option_d_explanation": self.option_explanations.get("D", ""),
            "option_e_explanation": self.option_explanations.get("E", ""),
            "source_basis": self.source_basis,
            "quality_score": self.quality_score,
            "review_status": self.review_status,
            "revision_notes": self.revision_notes,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }


EXPORT_COLUMNS: tuple[str, ...] = (
    "question_id",
    "chapter_id",
    "chapter_title",
    "section_title",
    "source_chunk_id",
    "source_paragraph_range",
    "tested_concept",
    "question_type",
    "difficulty",
    "stem",
    "option_a",
    "option_b",
    "option_c",
    "option_d",
    "option_e",
    "correct_answer",
    "explanation",
    "option_a_explanation",
    "option_b_explanation",
    "option_c_explanation",
    "option_d_explanation",
    "option_e_explanation",
    "source_basis",
    "quality_score",
    "review_status",
    "revision_notes",
    "created_at",
    "updated_at",
)
