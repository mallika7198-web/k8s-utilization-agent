import json
from pathlib import Path

from tracker import append_change


def test_append_change_creates_and_appends(tmp_path):
    tracker_file = tmp_path / 'tracker.json'
    initial = {
        'last_updated': '2020-01-01T00:00:00Z',
        'todos': [],
        'changes': [
            {'timestamp': '2020-01-01T00:00:00Z', 'files_modified': ['a'], 'type': 'init', 'description': 'init'}
        ],
        'notes': ''
    }
    tracker_file.write_text(json.dumps(initial, indent=2))

    entry = {'files_modified': ['x'], 'type': 'test', 'description': 'append test'}
    ok = append_change(entry, tracker_path=str(tracker_file))
    assert ok
    data = json.loads(tracker_file.read_text())
    assert 'changes' in data
    assert len(data['changes']) == 2
    assert data['changes'][-1]['files_modified'] == ['x']
