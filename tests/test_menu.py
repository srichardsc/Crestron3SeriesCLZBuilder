from __future__ import annotations

import io
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from crestron_clz_builder.menu import (
    _get_environment_info,
    _render_header,
    _render_menu,
    run_interactive_menu,
)


class MenuTests(unittest.TestCase):
    def test_get_environment_info(self) -> None:
        info = _get_environment_info()
        self.assertIn("root", info)
        self.assertIn("config_exists", info)
        self.assertIn("simpl_installed", info)

    def test_render_header_and_menu(self) -> None:
        info = {
            "root": "C:/fake/path",
            "config_exists": True,
            "config_name": "clz-builder.json",
            "project_name": "Driver.csproj",
            "assembly_name": "Driver",
            "version_str": "1.0.0.0",
            "simpl_installed": True,
            "simpl_installer": None,
        }
        stdout = io.StringIO()
        with patch("sys.stdout", stdout):
            _render_header(info)
            _render_menu()
        output = stdout.getvalue()
        self.assertIn("Crestron 3-Series / 4-Series CLZ Builder", output)
        self.assertIn("[1] Quick Build (Run)", output)
        self.assertIn("[2] Guided Setup Wizard", output)
        self.assertIn("[3] System Diagnostics (Doctor)", output)
        self.assertIn("[4] Install Crestron SIMPL# Pro SDK", output)
        self.assertIn("[0] Exit", output)

    def test_menu_exit_option(self) -> None:
        stdout = io.StringIO()
        with patch("sys.stdout", stdout), patch("builtins.input", side_effect=["0"]):
            code = run_interactive_menu()
            self.assertEqual(code, 0)
        self.assertIn("Exiting CLZ Builder. Goodbye!", stdout.getvalue())

    def test_menu_keyboard_interrupt(self) -> None:
        stdout = io.StringIO()
        with patch("sys.stdout", stdout), patch("builtins.input", side_effect=KeyboardInterrupt):
            code = run_interactive_menu()
            self.assertEqual(code, 0)
        self.assertIn("Operation cancelled. Exiting CLZ Builder.", stdout.getvalue())

    def test_menu_eof(self) -> None:
        stdout = io.StringIO()
        with patch("sys.stdout", stdout), patch("builtins.input", side_effect=EOFError):
            code = run_interactive_menu()
            self.assertEqual(code, 0)
        self.assertIn("Exiting CLZ Builder.", stdout.getvalue())

    def test_menu_invalid_then_exit(self) -> None:
        stdout = io.StringIO()
        with patch("sys.stdout", stdout), patch("builtins.input", side_effect=["99", "", "0"]):
            code = run_interactive_menu()
            self.assertEqual(code, 0)
        self.assertIn("Invalid option '99'", stdout.getvalue())

    def test_menu_enter_to_recompile_when_ready(self) -> None:
        ready_info = {
            "root": "C:/fake/path",
            "config_exists": True,
            "config_name": "clz-builder.json",
            "project_name": "Driver.csproj",
            "assembly_name": "Driver",
            "version_str": "1.0.0.0",
            "simpl_installed": True,
            "simpl_installer": None,
        }
        stdout = io.StringIO()
        with patch("crestron_clz_builder.menu._get_environment_info", return_value=ready_info), \
             patch("sys.stdout", stdout), \
             patch("crestron_clz_builder.menu._action_quick_build", return_value="exit") as mock_build, \
             patch("builtins.input", side_effect=[""]):  # User presses Enter
            code = run_interactive_menu()
            self.assertEqual(code, 0)
            mock_build.assert_called_once()
        self.assertIn(">>> Everything is ready. Just press [Enter] to Recompile.", stdout.getvalue())


if __name__ == "__main__":
    unittest.main()
