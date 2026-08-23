from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from crestron_clz_builder.cli import main


class CliTests(unittest.TestCase):
    def test_init_writes_versioned_config_without_sdk(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "driver.csproj").write_text("<Project />", encoding="utf-8")
            self.assertEqual(main(["init", "--config", str(root / "builder.json"), "--project", "driver.csproj"]), 0)
            text = (root / "builder.json").read_text(encoding="utf-8")
            self.assertIn('"schema": 1', text)
            self.assertIn('"modules": []', text)
