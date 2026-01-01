"""
Tracker module for recording changes
"""
import json
from datetime import datetime


def append_change(files_modified, change_type, description):
    """Append a change to tracker.json"""
    try:
        with open('tracker.json', 'r') as f:
            changes = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        changes = []
    
    change = {
        'timestamp': datetime.utcnow().isoformat() + 'Z',
        'files_modified': files_modified,
        'change_type': change_type,
        'description': description
    }
    
    changes.append(change)
    
    with open('tracker.json', 'w') as f:
        json.dump(changes, f, indent=2)
