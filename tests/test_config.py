from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from crestron_clz_builder.config import ConfigError, load_config
from crestron_clz_builder.builder import stable_mvid
from crestron_clz_builder.builder import BuildError, _validate_sources


class ConfigTests(unittest.TestCase):
    def write_config(self, root: Path, value: dict) -> Path:
        path = root / "builder.json"
        path.write_text(json.dumps(value), encoding="utf-8")
        return path

    def test_modules_are_optional_for_assembly_only_packages(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "driver.csproj").write_text(
                '<Project xmlns="http://schemas.microsoft.com/developer/msbuild/2003"><PropertyGroup><AssemblyName>Example</AssemblyName></PropertyGroup></Project>',
                encoding="utf-8",
            )
            config = load_config(self.write_config(root, {"schema": 1, "assembly": {"project": "driver.csproj"}, "targets": ["series3"]}))
            self.assertEqual(config.modules, ())
            self.assertEqual(config.effective_assembly_name(), "Example")

    def test_rejects_unknown_target_and_root_escape(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            base = {"schema": 1, "assembly": {"project": "driver.csproj"}, "modules": []}
            with self.assertRaises(ConfigError):
                load_config(self.write_config(root, {**base, "targets": ["series2"]}))
            with self.assertRaises(ConfigError):
                load_config(self.write_config(root, {**base, "assembly": {"project": "../outside.csproj"}}))

    def test_rejects_schema_drift(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            with self.assertRaises(ConfigError):
                load_config(self.write_config(Path(temporary), {"schema": 2, "assembly": {"project": "driver.csproj"}, "modules": []}))

    def test_mvid_ignores_local_output_targets_and_tool_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            project = root / "driver.csproj"
            project.write_text("<Project><PropertyGroup><AssemblyName>Example</AssemblyName></PropertyGroup></Project>", encoding="utf-8")
            (root / "Driver.cs").write_text("public class Driver {}", encoding="utf-8")
            (root / "toolchain.lock.json").write_text('{"schema":1,"signerThumbprint":"x","runtime":{"fingerprintSha256":"r"},"inputs":{}}', encoding="utf-8")
            common = {"schema": 1, "assembly": {"project": "driver.csproj", "name": "Example"}, "modules": [], "package": {"metadata": {"friendlyName": "Example", "systemName": "Example", "entryPoint": "Example"}}}
            first = load_config(self.write_config(root, {**common, "targets": ["series3"], "output": {"build": "one", "dist": "dist-one"}, "toolchain": {"paths": {"msbuild": "sdk/a.exe"}}}))
            second = load_config(self.write_config(root, {**common, "targets": ["series4"], "output": {"build": "two", "dist": "dist-two"}, "toolchain": {"paths": {"msbuild": "sdk/b.exe"}}}))
            self.assertEqual(stable_mvid(first, root / "toolchain.lock.json", "Example"), stable_mvid(second, root / "toolchain.lock.json", "Example"))

    def test_rejects_overlapping_output_directories(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = {"schema": 1, "assembly": {"project": "driver.csproj"}, "modules": [], "output": {"build": "build", "dist": "build/dist"}}
            with self.assertRaises(ConfigError):
                load_config(self.write_config(root, value))

    def test_rejects_unknown_assembly_output_placeholder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = {
                "schema": 1,
                "assembly": {"project": "driver.csproj", "output": "bin/{machine}/{name}.dll"},
                "modules": [],
            }
            with self.assertRaises(ConfigError):
                load_config(self.write_config(root, value))

    def test_rejects_reserved_windows_assembly_name(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = {"schema": 1, "assembly": {"project": "driver.csproj", "name": "CON"}, "modules": []}
            with self.assertRaises(ConfigError):
                load_config(self.write_config(root, value))

    def test_rejects_configurable_local_state_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = {
                "schema": 1,
                "assembly": {"project": "driver.csproj"},
                "modules": [],
                "toolchain": {"localCache": "source.cs"},
            }
            with self.assertRaises(ConfigError):
                load_config(self.write_config(root, value))

    def test_rejects_output_directory_containing_project_source(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            value = {
                "schema": 1,
                "assembly": {"project": "Project/Driver.csproj"},
                "modules": [],
                "output": {"build": "Project", "dist": "dist"},
            }
            with self.assertRaises(ConfigError):
                load_config(self.write_config(root, value))

    def test_rejects_reserved_package_filenames(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "driver.csproj").write_text("<Project />", encoding="utf-8")
            (root / "Example.dll").write_bytes(b"x")
            value = {"schema": 1, "assembly": {"project": "driver.csproj", "name": "Example"}, "modules": [], "package": {"dependencies": ["Example.dll"]}}
            config = load_config(self.write_config(root, value))
            with self.assertRaises(BuildError):
                _validate_sources(config, "Example")
