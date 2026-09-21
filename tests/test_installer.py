from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from crestron_clz_builder.cli import main
from crestron_clz_builder.installer import (
    find_simpl_sharp_installer,
    is_simpl_sharp_installed,
    is_vs2008_sp1_bypass_installed,
    INSTALLER_PATTERNS,
)


class InstallerTests(unittest.TestCase):
    def test_find_installer_empty(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            empty_dir = Path(temporary)
            self.assertIsNone(find_simpl_sharp_installer(search_paths=[empty_dir], include_defaults=False))

    def test_find_installer_patterns(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            installer = root / "crestron_simpl_sharp_pro_2.000.0058.01.exe"
            installer.write_bytes(b"MZ\x00\x00")
            found = find_simpl_sharp_installer(search_paths=[root], include_defaults=False)
            self.assertIsNotNone(found)
            self.assertEqual(found.resolve(), installer.resolve())

    def test_find_installer_in_source_subfolder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            source_dir = root / ".source"
            source_dir.mkdir()
            installer = source_dir / "crestron_simpl_sharp_pro.exe"
            installer.write_bytes(b"MZ\x00\x00")
            found = find_simpl_sharp_installer(search_paths=[root, source_dir], include_defaults=False)
            self.assertIsNotNone(found)
            self.assertEqual(found.resolve(), installer.resolve())

    def test_find_installer_ignores_clz_builder(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            clz_exe = root / "clz-builder.exe"
            clz_exe.write_bytes(b"MZ\x00\x00")
            self.assertIsNone(find_simpl_sharp_installer(search_paths=[root], include_defaults=False))

    def test_is_vs2008_sp1_bypass_installed_returns_bool(self) -> None:
        result = is_vs2008_sp1_bypass_installed()
        self.assertIsInstance(result, bool)

    def test_cli_install_prereqs_help(self) -> None:
        with self.assertRaises(SystemExit) as cm:
            main(["install-prereqs", "--help"])
        self.assertEqual(cm.exception.code, 0)

    def test_cli_install_prereqs_missing_installer(self) -> None:
        with patch("crestron_clz_builder.installer.is_simpl_sharp_installed", return_value=False), \
             patch("crestron_clz_builder.installer.find_simpl_sharp_installer", return_value=None):
            exit_code = main(["install-prereqs"])
            self.assertEqual(exit_code, 2)


if __name__ == "__main__":
    unittest.main()
