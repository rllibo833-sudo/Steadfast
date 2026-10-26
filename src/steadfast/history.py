from __future__ import annotations

import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .pipeline import PipelineError, _inside


HISTORY_VERSION = 1
MAX_HISTORY_BYTES = 32 * 1024 * 1024


def _history_path(repo: Path, relative: str) -> Path:
    if not isinstance(relative, str) or not relative.strip():
        raise PipelineError('history path must be a non-empty repository-relative path')
    path = _inside(repo.resolve(), relative, 'history path')
    if path.exists() and (path.is_symlink() or not path.is_file()):
        raise PipelineError('history path must be a regular file, not a symlink or directory')
    return path


def record_run(repo: Path, relative: str, result: dict[str, Any]) -> dict[str, Any]:
    '''Append one immutable JSONL execution record; never overwrite prior runs.'''
    if not isinstance(result, dict) or result.get('tool') != 'steadfast':
        raise PipelineError('only a Steadfast pipeline result can be recorded')
    path = _history_path(repo, relative)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size > MAX_HISTORY_BYTES:
        raise PipelineError(f'history exceeds {MAX_HISTORY_BYTES} bytes; archive it before recording')
    record = {
        'schema_version': HISTORY_VERSION,
        'run_id': uuid.uuid4().hex,
        'recorded_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'passed': bool(result.get('passed')),
        'duration_seconds': result.get('duration_seconds'),
        'summary': result.get('summary', {}),
        'manifest': result.get('manifest', ''),
        'steps': result.get('steps', []),
    }
    payload = (json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n').encode('utf-8')
    flags = os.O_WRONLY | os.O_CREAT | os.O_APPEND
    if hasattr(os, 'O_NOFOLLOW'):
        flags |= os.O_NOFOLLOW
    fd = os.open(path, flags, 0o600)
    try:
        written = os.write(fd, payload)
        if written != len(payload):
            raise OSError('short write while appending pipeline history record')
    finally:
        os.close(fd)
    return record


def read_history(repo: Path, relative: str = '.steadfast/runs.jsonl', *, limit: int = 20, status: str = 'all') -> dict[str, Any]:
    '''Read recent run records; reject corrupt complete lines instead of hiding them.'''
    if not isinstance(limit, int) or isinstance(limit, bool) or not 1 <= limit <= 1000:
        raise PipelineError('history limit must be from 1 to 1000')
    if status not in {'all', 'passed', 'failed'}:
        raise PipelineError('history status must be all, passed, or failed')
    path = _history_path(repo.resolve(), relative)
    if not path.exists():
        return {'history': relative, 'count': 0, 'runs': []}
    size = path.stat().st_size
    if size > MAX_HISTORY_BYTES:
        raise PipelineError(f'history exceeds {MAX_HISTORY_BYTES} bytes; archive it before reading')
    try:
        raw = path.read_text(encoding='utf-8')
    except (OSError, UnicodeError) as exc:
        raise PipelineError(f'cannot read pipeline history: {exc}') from exc
    lines = raw.splitlines()
    records: list[dict[str, Any]] = []
    for index, line in enumerate(lines, start=1):
        if not line.strip():
            continue
        try:
            item = json.loads(line)
        except json.JSONDecodeError as exc:
            if index == len(lines) and not raw.endswith('\n'):
                continue
            raise PipelineError(f'invalid history JSON on line {index}: {exc.msg}') from exc
        if (not isinstance(item, dict) or item.get('schema_version') != HISTORY_VERSION
                or not isinstance(item.get('run_id'), str)
                or not isinstance(item.get('passed'), bool)
                or not isinstance(item.get('steps'), list)):
            raise PipelineError(f'invalid history record schema on line {index}')
        if status == 'all' or item['passed'] == (status == 'passed'):
            records.append(item)
    recent = list(reversed(records[-limit:]))
    return {'history': relative, 'count': len(recent), 'runs': recent}
