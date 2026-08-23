from __future__ import annotations

import json
from pathlib import Path
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from crestron_clz_builder.config import load_config
from crestron_clz_builder.toolchain import resolve_tools, runtime_identity, verify_lock, write_lock


class ToolchainCacheTests(unittest.TestCase):
    def test_runtime_identity_pins_loaded_zlib_binary(self) -> None:
        zlib_data = runtime_identity()["zlib"]
        self.assertTrue("moduleFileSha256" in zlib_data or zlib_data.get("embeddedInPython") is True)

    def test_resolved_paths_are_cached_but_lock_has_no_paths(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            (root / "driver.csproj").write_text("<Project />", encoding="utf-8")
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
                path.mkdir()
                paths[name] = str(path)
            config_path = root / "builder.json"
            config_path.write_text(json.dumps({
                "schema": 1,
                "assembly": {"project": "driver.csproj", "name": "Example"},
                "modules": [],
                "toolchain": {"paths": paths},
            }), encoding="utf-8")
            config = load_config(config_path)
            resolved = resolve_tools(config)
            self.assertTrue(config.resolved_local_cache_path.is_file())
            cache = json.loads(config.resolved_local_cache_path.read_text(encoding="utf-8"))
            self.assertEqual(cache["schema"], 1)
            self.assertEqual(Path(cache["paths"]["msbuild"]), resolved["msbuild"])
            lock_path = write_lock(config, resolved)
            verify_lock(config, resolved)
            lock_text = lock_path.read_text(encoding="utf-8")
            self.assertNotIn(str(root), lock_text)
