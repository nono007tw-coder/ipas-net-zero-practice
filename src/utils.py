from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Iterable


def read_json(path: Path) -> Any:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8-sig").splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        value = json.loads(stripped)
        if not isinstance(value, dict):
            raise ValueError(f"{path}:{line_number} must contain a JSON object")
        rows.append(value)
    return rows


def write_jsonl(path: Path, rows: Iterable[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    content = "\n".join(json.dumps(row, ensure_ascii=False) for row in rows)
    path.write_text(content + ("\n" if content else ""), encoding="utf-8")


def load_records(path: Path) -> list[dict[str, Any]]:
    if path.suffix.lower() == ".jsonl":
        return read_jsonl(path)
    payload = read_json(path)
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if isinstance(payload, dict):
        return [payload]
    raise ValueError(f"Unsupported JSON payload in {path}")


def load_records_from_directory(directory: Path) -> list[dict[str, Any]]:
    if not directory.exists():
        raise FileNotFoundError(f"Directory not found: {directory}")
    records: list[dict[str, Any]] = []
    for path in sorted(directory.glob("*.json")):
        records.extend(load_records(path))
    for path in sorted(directory.glob("*.jsonl")):
        records.extend(load_records(path))
    return records


def render_template(template_path: Path, replacements: dict[str, str]) -> str:
    if not template_path.exists():
        raise FileNotFoundError(f"Prompt template not found: {template_path}")
    content = template_path.read_text(encoding="utf-8-sig")
    for key, value in replacements.items():
        content = content.replace(f"{{{{{key}}}}}", value)
    unresolved = sorted(set(re.findall(r"\{\{([a-zA-Z0-9_]+)\}\}", content)))
    if unresolved:
        raise ValueError(f"Unresolved prompt placeholders: {', '.join(unresolved)}")
    return content


def normalize_text(value: str) -> str:
    lowered = value.casefold()
    lowered = re.sub(r"[^a-z0-9\s]", " ", lowered)
    return " ".join(lowered.split())


def chapter_number(chapter_id: str) -> int:
    match = re.fullmatch(r"CH(\d{3})", chapter_id)
    if not match:
        raise ValueError(f"Invalid chapter ID: {chapter_id}; expected CH001-CH085")
    number = int(match.group(1))
    if not 1 <= number <= 85:
        raise ValueError(f"Chapter ID out of range: {chapter_id}")
    return number


def ensure_unique(values: Iterable[str], label: str) -> None:
    seen: set[str] = set()
    duplicates: set[str] = set()
    for value in values:
        if value in seen:
            duplicates.add(value)
        seen.add(value)
    if duplicates:
        raise ValueError(f"Duplicate {label}: {', '.join(sorted(duplicates))}")


def compact_question_summary(records: Iterable[dict[str, Any]]) -> list[dict[str, str]]:
    return [
        {
            "question_id": str(item.get("question_id", "")),
            "tested_concept": str(item.get("tested_concept", "")),
            "stem": str(item.get("stem", ""))[:240],
            "correct_answer_text": str(
                item.get("options", {}).get(str(item.get("correct_answer", "")), "")
                if isinstance(item.get("options"), dict)
                else ""
            )[:160],
        }
        for item in records
    ]
