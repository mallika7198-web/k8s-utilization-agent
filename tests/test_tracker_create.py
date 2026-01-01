import os
import json
from tracker import append_change


def test_append_creates_file_when_missing(tmp_path):
    p = tmp_path / 't.json'
    entry = {'files_modified': ['a'], 'type': 'x', 'description': 'create test'}
    ok = append_change(entry, tracker_path=str(p))
    assert ok
    data = json.loads(p.read_text())
    assert 'changes' in data and len(data['changes']) == 1
