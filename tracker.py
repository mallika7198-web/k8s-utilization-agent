"""Utility for append-only tracker.json updates.
Provides a deterministic append operation that writes atomically.
"""
import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _atomic_write(path: str, data: str) -> None:
    dirp = os.path.dirname(path) or '.'
    fd, tmp = tempfile.mkstemp(prefix='.tmp_tracker_', dir=dirp)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as f:
            f.write(data)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            try:
                os.remove(tmp)
            except Exception:
                pass


def append_change(entry: Dict[str, Any], tracker_path: str = '.tracker.json') -> bool:
    """Append a change entry to tracker_path in an append-only manner.

    Returns True on success, False on failure.
    """
    try:
        if not os.path.exists(tracker_path):
            # Create minimal structure if missing
            base = {'last_updated': _now_iso(), 'todos': [], 'changes': [], 'notes': ''}
        else:
            with open(tracker_path, 'r', encoding='utf-8') as f:
                base = json.load(f)

        changes = base.get('changes') or []
        # Append the new entry (do not attempt to remove or reorder existing entries)
        entry_with_ts = dict(entry)
        if 'timestamp' not in entry_with_ts:
            entry_with_ts['timestamp'] = _now_iso()
        changes.append(entry_with_ts)
        base['changes'] = changes
        base['last_updated'] = _now_iso()

        _atomic_write(tracker_path, json.dumps(base, indent=2))
        return True
    except Exception:
        return False
