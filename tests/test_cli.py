import tempfile
import unittest
from pathlib import Path
from steadfast.cli import main

class CliTests(unittest.TestCase):
    def test_init_and_evidence_check(self):
        with tempfile.TemporaryDirectory() as d:
            self.assertEqual(main(["--repo", d, "init"]), 0)
            self.assertEqual(main(["--repo", d, "evidence-check"]), 0)

if __name__ == "__main__":
    unittest.main()
