from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class EvidenceRecord:
    """A single auditable verification claim with explicit command and outcome."""
    claim: str
    command: str
    exit_code: int
    result: str
    verified_at: str
    commit: str = ""
    environment: str = ""
    limitations: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_record(value: Any) -> list[str]:
    errors: list[str] = []
    if not isinstance(value, dict):
        return ["record must be a JSON object"]
    for key in ("claim", "command", "result", "verified_at"):
        if not isinstance(value.get(key), str) or not value[key].strip():
            errors.append(f"{key} must be a non-empty string")
    code = value.get("exit_code")
    if not isinstance(code, int) or isinstance(code, bool):
        errors.append("exit_code must be an integer")
    timestamp = value.get("verified_at")
    if isinstance(timestamp, str) and timestamp.strip():
        try:
            datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
        except ValueError:
            errors.append("verified_at must be an ISO-8601 timestamp")
    for key in ("commit", "environment", "limitations"):
        if key in value and not isinstance(value[key], str):
            errors.append(f"{key} must be a string when provided")
    return errors


def new_record(
    claim: str,
    command: str,
    exit_code: int,
    result: str,
    *,
    commit: str = "",
    environment: str = "",
    limitations: str = "",
) -> EvidenceRecord:
    """Create a timestamped record; callers must supply the actual observed result."""
    return EvidenceRecord(
        claim=claim,
        command=command,
        exit_code=exit_code,
        result=result,
        verified_at=datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        commit=commit,
        environment=environment,
        limitations=limitations,
    )


def load_records(path: Path) -> tuple[list[dict[str, Any]], list[str]]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return [], [f"evidence file not found: {path}"]
    except (OSError, UnicodeError, json.JSONDecodeError) as exc:
        return [], [f"evidence file is unreadable or invalid JSON: {exc}"]
    if not isinstance(raw, list):
        return [], ["evidence document root must be a JSON array"]
    errors: list[str] = []
    records: list[dict[str, Any]] = []
    for index, item in enumerate(raw):
        for message in validate_record(item):
            errors.append(f"record[{index}]: {message}")
        if not validate_record(item):
            records.append(item)
    return records, errors


def save_records(path: Path, records: list[dict[str, Any]]) -> None:
    """Atomically replace a structured evidence file after validating all records."""
    errors: list[str] = []
    for index, item in enumerate(records):
        errors.extend(f"record[{index}]: {error}" for error in validate_record(item))
    if errors:
        raise ValueError("; ".join(errors))
    path.parent.mkdir(parents=True, exist_ok=True)
    temp = path.with_suffix(path.suffix + ".tmp")
    temp.write_text(json.dumps(records, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    temp.replace(path)
