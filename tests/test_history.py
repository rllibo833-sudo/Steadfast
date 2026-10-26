import json
import tempfile
import unittest
from pathlib import Path

from steadfast.history import read_history, record_run
from steadfast.pipeline import PipelineError


class PipelineHistoryTests(unittest.TestCase):
    def result(self, passed):
        return {'tool': 'steadfast', 'passed': passed, 'manifest': '.steadfast/pipeline.json',
                'duration_seconds': 0.25, 'summary': {'passed': int(passed), 'failed': int(not passed)},
                'steps': []}

    def test_appends_runs_and_filters_latest_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            record_run(root, '.steadfast/runs.jsonl', self.result(True))
            record_run(root, '.steadfast/runs.jsonl', self.result(False))
            record_run(root, '.steadfast/runs.jsonl', self.result(True))
            recent = read_history(root, limit=2)
            self.assertEqual(recent['count'], 2)
            self.assertEqual([run['passed'] for run in recent['runs']], [True, False])
            self.assertEqual(read_history(root, status='failed')['count'], 1)
            lines = (root / '.steadfast/runs.jsonl').read_text(encoding='utf-8').splitlines()
            self.assertEqual(len(lines), 3)
            self.assertEqual(len({json.loads(line)['run_id'] for line in lines}), 3)

    def test_rejects_path_escape_and_corrupt_history(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(PipelineError, 'repository-relative'):
                record_run(root, '../outside.jsonl', self.result(True))
            path = root / '.steadfast' / 'runs.jsonl'
            path.parent.mkdir()
            path.write_text('{"schema_version":1,"run_id":"abc","passed":true,"steps":[]}\nnot-json\n', encoding='utf-8')
            with self.assertRaisesRegex(PipelineError, 'line 2'):
                read_history(root)

    def test_missing_history_is_empty_and_invalid_limit_fails(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.assertEqual(read_history(root)['runs'], [])
            with self.assertRaisesRegex(PipelineError, 'limit'):
                read_history(root, limit=0)


if __name__ == '__main__':
    unittest.main()
