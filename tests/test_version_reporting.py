from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from steadfast import __version__
from steadfast.checks import run_audit
from steadfast.inventory import inventory_report
from steadfast.policy import init_policy


class VersionReportingTests(unittest.TestCase):
    def test_audit_reports_package_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_policy(repo)
            self.assertEqual(run_audit(repo)["version"], __version__)

    def test_inventory_reports_package_version(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            repo = Path(directory)
            init_policy(repo)
            self.assertEqual(inventory_report(repo)["version"], __version__)


if __name__ == "__main__":
    unittest.main()
