from __future__ import annotations

import io
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from crestron_clz_builder.cli import main, _print_checklist
from crestron_clz_builder.config import TOOL_NAMES
from crestron_clz_builder.toolchain import probe_toolchain


def write_minimal_host(root: Path) -> dict[str, str]:
    """Create a fake complete toolchain under root and return its tool paths."""
    sdk = root / "sdk"
    files = [
        "msbuild", "csc", "helperCsc", "spluscc", "compiler", "services", "ionic", "cecil",
        "cf_mscorlib", "cf_system", "cf_system_core", "cf_csc_rsp", "cf_common_targets", "cf_csharp_targets",
        "msbuild_rsp", "helper_system", "helper_reference", "custom_attributes", "data_file", "data_signature",
    ]
    paths: dict[str, str] = {}
    for name in files:
        path = sdk / (name + ".bin")
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(name.encode("ascii"))
        paths[name] = str(path)
    for name in ("cresdb", "cf", "references", "data"):
        path = sdk / name
        path.mkdir(exist_ok=True)
        paths[name] = str(path)
    return paths


def write_bogus_paths(root: Path) -> dict[str, str]:
    """Point every named input at a guaranteed-missing location.

    This keeps tests hermetic on hosts that do have the real SDK installed:
    explicit config paths always win over autodetection.
    """
    return {name: str(root / "definitely-missing" / name) for name in TOOL_NAMES}


class ProbeTests(unittest.TestCase):
    def test_probe_reports_every_missing_input_without_raising(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "driver.csproj").write_text("<Project />", encoding="utf-8")
            config_path = root / "builder.json"
            config_path.write_text(json.dumps({
                "schema": 1,
                "assembly": {"project": "driver.csproj", "name": "Example"},
                "modules": [],
                "toolchain": {"paths": write_bogus_paths(root)},
            }), encoding="utf-8")
            from crestron_clz_builder.config import load_config
            probes = probe_toolchain(load_config(config_path))
            self.assertTrue(len(probes) >= 20)
            missing = {probe.name for probe in probes if not probe.ok}
            self.assertIn("spluscc", missing)
            for probe in probes:
                self.assertFalse(probe.ok, f"{probe.name} must report missing under bogus paths")
                self.assertTrue(probe.fix, f"{probe.name} must carry a fix hint")

    def test_probe_reports_all_missing_when_paths_are_wrong(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "driver.csproj").write_text("<Project />", encoding="utf-8")
            config_path = root / "builder.json"
            config_path.write_text(json.dumps({
                "schema": 1,
                "assembly": {"project": "driver.csproj", "name": "Example"},
                "modules": [],
                "toolchain": {"paths": {"msbuild": str(root / "nope" / "MSBuild.exe")}},
            }), encoding="utf-8")
            from crestron_clz_builder.config import load_config
            probes = probe_toolchain(load_config(config_path))
            by_name = {probe.name: probe for probe in probes}
            self.assertFalse(by_name["msbuild"].ok)
            self.assertIsNotNone(by_name["msbuild"].expected_path)

    def test_probe_matches_resolver_when_complete(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "driver.csproj").write_text("<Project />", encoding="utf-8")
            config_path = root / "builder.json"
            config_path.write_text(json.dumps({
                "schema": 1,
                "assembly": {"project": "driver.csproj", "name": "Example"},
                "modules": [],
                "toolchain": {"paths": write_minimal_host(root)},
            }), encoding="utf-8")
            from crestron_clz_builder.config import load_config
            config = load_config(config_path)
            probes = {probe.name: probe for probe in probe_toolchain(config)}
            resolved = set(__import__("crestron_clz_builder.toolchain", fromlist=["resolve_tools"]).resolve_tools(config))
            for name in resolved:
                self.assertTrue(probes[name].ok, f"{name} should be OK when resolve_tools succeeds")


class ChecklistTests(unittest.TestCase):
    def make_probe(self, name: str, ok: bool):
        from crestron_clz_builder.toolchain import ToolchainProbe
        return ToolchainProbe(name, f"label-{name}", f"component-{name}", "licensed", f"fix-{name}", None, ok)

    def test_checklist_exit_two_and_lists_fixes(self) -> None:
        buffer = io.StringIO()
        with patch("sys.stdout", buffer):
            code = _print_checklist([self.make_probe("a", True), self.make_probe("b", False)])
        output = buffer.getvalue()
        self.assertEqual(code, 2)
        self.assertIn("[OK]", output)
        self.assertIn("[MISSING]", output)
        self.assertIn("fix-fix-b", output.replace("\n", "").replace("fix: fix-b", "fix-fix-b"))
        self.assertIn("authorized Crestron dealer channel", output)

    def test_checklist_exit_zero_when_complete(self) -> None:
        buffer = io.StringIO()
        with patch("sys.stdout", buffer):
            code = _print_checklist([self.make_probe("a", True)])
        self.assertEqual(code, 0)
        self.assertIn("1/1 inputs ready", buffer.getvalue())


class SetupWizardTests(unittest.TestCase):
    def test_setup_non_interactive_creates_config_and_fails_clean_when_toolchain_missing(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Driver.csproj").write_text("<Project />", encoding="utf-8")
            # Pre-seed a config whose toolchain paths are guaranteed missing so
            # the expectation holds on any host, including fully licensed ones.
            seeded = {
                "schema": 1,
                "assembly": {"project": "Driver.csproj", "name": "Driver"},
                "modules": [],
                "toolchain": {"paths": write_bogus_paths(root)},
            }
            (root / "clz-builder.json").write_text(json.dumps(seeded), encoding="utf-8")
            with patch("crestron_clz_builder.cli.Path.cwd", return_value=root), \
                 patch("sys.stdin", io.StringIO("")):
                code = main(["setup", "--project", "Driver.csproj", "--non-interactive"])
            self.assertEqual(code, 2)
            kept = json.loads((root / "clz-builder.json").read_text(encoding="utf-8"))
            self.assertEqual(kept["assembly"]["project"], "Driver.csproj")
            self.assertFalse((root / "toolchain.lock.json").exists())

    def test_setup_reuses_existing_config(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "Driver.csproj").write_text("<Project />", encoding="utf-8")
            existing = {
                "schema": 1,
                "assembly": {"project": "Driver.csproj", "name": "Kept"},
                "modules": [],
            }
            (root / "my-config.json").write_text(json.dumps(existing), encoding="utf-8")
            with patch("crestron_clz_builder.cli.Path.cwd", return_value=root):
                main(["setup", "--config", "my-config.json", "--non-interactive"])
            kept = json.loads((root / "my-config.json").read_text(encoding="utf-8"))
            self.assertEqual(kept["assembly"]["name"], "Kept")


class DoctorHumanOutputTests(unittest.TestCase):
    def test_doctor_human_mode_prints_checklist_and_exits_two(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "driver.csproj").write_text("<Project />", encoding="utf-8")
            config_path = root / "builder.json"
            config_path.write_text(json.dumps({
                "schema": 1,
                "assembly": {"project": "driver.csproj", "name": "Example"},
                "modules": [],
                "toolchain": {"paths": write_bogus_paths(root)},
            }), encoding="utf-8")
            buffer = io.StringIO()
            with patch("sys.stdout", buffer):
                code = main(["doctor", "--config", str(config_path)])
            output = buffer.getvalue()
            self.assertEqual(code, 2)
            self.assertIn("[MISSING]", output)
            self.assertIn("[OK]", output.replace("[MISSING]", "[OK]"))  # at least one mark rendered
            self.assertIn("toolchain:", output)


if __name__ == "__main__":
    unittest.main()
