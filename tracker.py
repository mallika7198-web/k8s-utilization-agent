"""
Tracker module for recording changes
"""
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List, Optional, Union

logger = logging.getLogger(__name__)

# Default tracker file path
DEFAULT_TRACKER_PATH = Path(__file__).parent / 'tracker.json'


def append_change(
    change_data: Union[Dict[str, Any], List[str]],
    change_type: Optional[str] = None,
    description: Optional[str] = None,
    tracker_path: Optional[str] = None
) -> None:
    """Append a change to tracker.json
    
    Supports two call signatures for backward compatibility:
    
    1. Dict-based (new style):
       append_change({
           'files_modified': ['file1.py', 'file2.py'],
           'type': 'analysis',
           'description': 'What changed'
       })
    
    2. Positional args (legacy style):
       append_change(['file1.py'], 'analysis', 'What changed')
    
    Args:
        change_data: Either a dict with change info OR a list of files (legacy)
        change_type: Type of change (only used in legacy mode)
        description: Description (only used in legacy mode)
        tracker_path: Optional path to tracker file (default: tracker.json)
    """
    path = Path(tracker_path) if tracker_path else DEFAULT_TRACKER_PATH
    
    # Handle both calling conventions
    if isinstance(change_data, dict):
        # New dict-based style
        files_modified = change_data.get('files_modified', [])
        change_type = change_data.get('type') or change_data.get('change_type', 'unknown')
        description = change_data.get('description', '')
    else:
        # Legacy positional style
        files_modified = change_data if isinstance(change_data, list) else []
        change_type = change_type or 'unknown'
        description = description or ''
    
    try:
        if path.exists():
            with open(path, 'r') as f:
                changes = json.load(f)
        else:
            changes = []
    except (json.JSONDecodeError, IOError) as e:
        logger.warning(f"Could not read tracker file, starting fresh: {e}")
        changes = []
    
    change = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'files_modified': files_modified,
        'change_type': change_type,
        'description': description
    }
    
    changes.append(change)
    
    try:
        with open(path, 'w') as f:
            json.dump(changes, f, indent=2)
        logger.debug(f"Appended change to tracker: {change_type}")
    except IOError as e:
        logger.error(f"Failed to write tracker file: {e}")
