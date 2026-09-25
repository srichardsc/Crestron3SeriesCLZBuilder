from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from crestron_clz_builder.config import ProjectConfig, load_config
from crestron_clz_builder.toolchain import resolve_tools


class SignerSandboxTests(unittest.TestCase):
    def test_dynamic_sandbox_patch_on_crestron_host(self) -> None:
        """Verify dynamic sandbox hashing and validation when Crestron SDK is installed."""
        config_path = Path(__file__).parents[1] / "examples" / "minimal.json"
        try:
            config = load_config(config_path)
            tools = resolve_tools(config)
        except Exception as ex:
            self.skipTest(f"Crestron toolchain not fully available: {ex}")

        with tempfile.TemporaryDirectory() as temporary:
            temp_dir = Path(temporary)
            helper = temp_dir / "Signer.exe"
            signer_source = Path(__file__).parents[1] / "src" / "crestron_clz_builder" / "Signer.cs"

            compile_cmd = [
                str(tools["helperCsc"]), "/nologo", "/noconfig", "/target:exe", "/platform:x86",
                f"/out:{helper}", f"/r:{tools['helper_system']}", f"/r:{tools['cecil']}",
                str(signer_source),
            ]
            result = subprocess.run(compile_cmd, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, f"Compilation failed: {result.stderr}")
            shutil.copy2(tools["cecil"], temp_dir / tools["cecil"].name)

            # Test patching on an assembly copy (e.g., custom_attributes dll)
            test_assembly = temp_dir / "TestAssembly.dll"
            shutil.copy2(tools["custom_attributes"], test_assembly)
            mvid = "00000000-0000-0000-0000-000000000001"

            patch_cmd = [
                str(helper), "patch", str(test_assembly),
                str(tools["cecil"]), str(tools["custom_attributes"]), mvid,
                str(tools["services"]), str(tools["compiler"]), str(tools["cresdb"]),
            ]
            patch_result = subprocess.run(patch_cmd, capture_output=True, text=True)
            self.assertEqual(patch_result.returncode, 0, f"Patch failed: {patch_result.stderr}\n{patch_result.stdout}")
            self.assertIn("metadata=patched", patch_result.stdout)
            self.assertIn("sandboxHash=", patch_result.stdout)
