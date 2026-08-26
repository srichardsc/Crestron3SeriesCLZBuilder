from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from crestron_clz_builder.cli import main
from crestron_clz_builder.config import ConfigError, TOOL_NAMES, bump_version


def bogus_paths(root: Path) -> dict[str, str]:
    """Guaranteed-missing toolchain paths so tests stay hermetic on licensed hosts."""
    return {name: str(root / "definitely-missing" / name) for name in TOOL_NAMES}


LEGACY_CSPROJ = """<Project DefaultTargets="Build" xmlns="http://schemas.microsoft.com/developer/msbuild/2003">
  <PropertyGroup>
    <AssemblyName>Demo</AssemblyName>
  </PropertyGroup>
</Project>"""


class BumpVersionTests(unittest.TestCase):
    def test_increments_last_component(self) -> None:
        self.assertEqual(bump_version("1.0.0.0"), ("1.0.0.1", "1.0.0.0"))
        self.assertEqual(bump_version("1.2.3.9"), ("1.2.3.10", "1.2.3.9"))

    def test_rejects_non_numeric_versions(self) -> None:
        with self.assertRaises(ConfigError):
            bump_version("1.0.0-beta")
        with self.assertRaises(ConfigError):
            bump_version("latest")


class RunCommandTests(unittest.TestCase):
    def make_project(self, root: Path) -> None:
        (root / "Driver.csproj").write_text(LEGACY_CSPROJ, encoding="utf-8")

    def test_first_run_creates_config_and_reports_missing_toolchain(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_project(root)
            buffer = io.StringIO()
            with patch("crestron_clz_builder.cli.Path.cwd", return_value=root), \
                 patch("sys.stdout", buffer):
                code = main(["run"])
            output = buffer.getvalue()
            # The bare host has no real SDK under the created config; the run
            # must stop cleanly at the toolchain gate with exit 1 from build().
            self.assertEqual(code, 1)
            config_path = root / "clz-builder.json"
            self.assertTrue(config_path.is_file())
            raw = json.loads(config_path.read_text(encoding="utf-8"))
            self.assertEqual(raw["assembly"]["project"], "Driver.csproj")
            self.assertEqual(raw["assembly"]["version"], "1.0.0.1")
            self.assertIn("version: 1.0.0.0 -> 1.0.0.1", output)

    def test_second_run_bumps_again(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_project(root)
            with patch("crestron_clz_builder.cli.Path.cwd", return_value=root), \
                 patch("sys.stdout", io.StringIO()):
                main(["run"])
                main(["run"])
            raw = json.loads((root / "clz-builder.json").read_text(encoding="utf-8"))
            self.assertEqual(raw["assembly"]["version"], "1.0.0.2")

    def test_existing_config_is_not_overwritten_by_flags(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_project(root)
            seeded = {
                "schema": 1,
                "assembly": {"project": "Driver.csproj", "name": "Kept"},
                "modules": [],
                "toolchain": {"paths": bogus_paths(root)},
            }
            (root / "clz-builder.json").write_text(json.dumps(seeded), encoding="utf-8")
            buffer = io.StringIO()
            with patch("crestron_clz_builder.cli.Path.cwd", return_value=root), \
                 patch("sys.stdout", buffer):
                code = main(["run", "--project", "Other.csproj"])
            output = buffer.getvalue()
            raw = json.loads((root / "clz-builder.json").read_text(encoding="utf-8"))
            self.assertEqual(raw["assembly"]["name"], "Kept")
            self.assertEqual(code, 1)
            self.assertIn("ignored because the configuration already exists", output)

    def test_no_bump_keeps_version(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_project(root)
            with patch("crestron_clz_builder.cli.Path.cwd", return_value=root), \
                 patch("sys.stdout", io.StringIO()):
                main(["run", "--no-bump"])
            raw = json.loads((root / "clz-builder.json").read_text(encoding="utf-8"))
            self.assertEqual(raw["assembly"]["version"], "1.0.0.0")

    def test_multiple_csproj_without_config_requires_explicit_project(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            self.make_project(root)
            (root / "Second" ).mkdir()
            (root / "Second" / "Other.csproj").write_text(LEGACY_CSPROJ, encoding="utf-8")
            buffer = io.StringIO()
            with patch("crestron_clz_builder.cli.Path.cwd", return_value=root), \
                 patch("sys.stderr", buffer):
                code = main(["run"])
            self.assertEqual(code, 1)
            self.assertFalse((root / "clz-builder.json").exists())
            self.assertIn("multiple .csproj candidates", buffer.getvalue())


if __name__ == "__main__":
    unittest.main()
