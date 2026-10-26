import tempfile
import unittest
from pathlib import Path

from steadfast.cli import main


class CliTests(unittest.TestCase):
    def test_init_and_evidence_check(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(main(["--repo", directory, "init"]), 0)
            self.assertEqual(main(["--repo", directory, "evidence-check"]), 0)

    def test_python_module_entrypoint_exists(self):
        self.assertTrue(
            (Path(__file__).parents[1] / "src" / "steadfast" / "__main__.py").is_file()
        )


if __name__ == "__main__":
    unittest.main()
