from __future__ import annotations

import json
from pathlib import Path
import shutil
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from crestron_clz_builder.builder import BuildError, publish_transaction
from crestron_clz_builder.config import load_config


class PublishTests(unittest.TestCase):
    def test_partial_install_failure_restores_every_previous_target(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            config_path = root / "clz-builder.json"
            config_path.write_text(
                json.dumps({
                    "schema": 1,
                    "assembly": {"project": "Project/Driver.csproj", "name": "Driver"},
                    "modules": [],
                    "output": {"build": "build", "dist": "dist"},
                }),
                encoding="utf-8",
            )
            config = load_config(config_path)
            publish = root / "staging"
            for target in ("series3", "series4"):
                (publish / target).mkdir(parents=True)
                (publish / target / "artifact.txt").write_text(f"new-{target}", encoding="utf-8")
                (root / "dist" / target).mkdir(parents=True)
                (root / "dist" / target / "artifact.txt").write_text(f"old-{target}", encoding="utf-8")

            real_move = shutil.move
            failed = False

            def partial_move(source: str, destination: str):
                nonlocal failed
                result = real_move(source, destination)
                if not failed and Path(source) == publish / "series4" and Path(destination) == root / "dist" / "series4":
                    failed = True
                    raise OSError("simulated post-move failure")
                return result

            with patch("crestron_clz_builder.builder.shutil.move", side_effect=partial_move):
                with self.assertRaises(BuildError):
                    publish_transaction(config, publish, ("series3", "series4"), "Release")

            for target in ("series3", "series4"):
                restored = root / "dist" / target / "artifact.txt"
                self.assertEqual(restored.read_text(encoding="utf-8"), f"old-{target}")
            self.assertFalse((root / "build" / "Release" / "publish-backup").exists())
