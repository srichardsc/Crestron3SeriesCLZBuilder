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

    def test_main_empty_args_non_interactive(self) -> None:
        from unittest.mock import MagicMock, patch
        mock_stdin = MagicMock()
        mock_stdin.isatty.return_value = False
        with patch("sys.stdin", mock_stdin), patch("sys.stdout"):
            self.assertEqual(main([]), 2)

    def test_main_menu_subcommand(self) -> None:
        from unittest.mock import patch
        with patch("crestron_clz_builder.menu.run_interactive_menu", return_value=0) as mock_menu:
            self.assertEqual(main(["menu"]), 0)
            mock_menu.assert_called_once()

    def test_main_interactive_flag(self) -> None:
        from unittest.mock import patch
        with patch("crestron_clz_builder.menu.run_interactive_menu", return_value=0) as mock_menu:
            self.assertEqual(main(["--interactive"]), 0)
            mock_menu.assert_called_once()
