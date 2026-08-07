from __future__ import annotations

import os
import subprocess
import sys
import unittest
from pathlib import Path


class ModuleEntrypointTests(unittest.TestCase):
    def test_module_help_succeeds(self) -> None:
        root = Path(__file__).resolve().parents[2]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(root / "src")

        result = subprocess.run(
            [sys.executable, "-m", "ostinato", "--help"],
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("doctor", result.stdout)
        self.assertIn("keyboard", result.stdout)

    def test_scripted_keyboard_input_succeeds(self) -> None:
        root = Path(__file__).resolve().parents[2]
        environment = os.environ.copy()
        environment["PYTHONPATH"] = str(root / "src")

        result = subprocess.run(
            [sys.executable, "-m", "ostinato", "keyboard", "--keys", "zaxgq"],
            cwd=root,
            env=environment,
            check=False,
            capture_output=True,
            text=True,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("chord changed to C", result.stdout)
        self.assertIn("chord changed to Gm", result.stdout)


if __name__ == "__main__":
    unittest.main()
