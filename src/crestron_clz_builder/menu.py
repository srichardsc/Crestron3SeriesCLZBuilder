"""Interactive terminal console for Crestron CLZ Builder."""

from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from . import __version__
from .builder import BuildError, BuildOptions, build
from .config import ConfigError, default_config, load_config
from .installer import find_simpl_sharp_installer, is_simpl_sharp_installed
from .toolchain import ToolchainError, probe_toolchain, resolve_tools, verify_lock, write_lock


def _pause(message: str = "\nPress Enter to return to the main menu...") -> None:
    """Wait for user acknowledgment so output remains visible."""
    try:
        input(message)
    except (EOFError, KeyboardInterrupt):
        print("")


def _get_environment_info() -> dict[str, Any]:
    """Gather diagnostic info about the current working environment."""
    root = Path.cwd().resolve()
    config_file = root / "clz-builder.json"
    config_exists = config_file.is_file()

    project_name = None
    assembly_name = None
    version_str = None

    if config_exists:
        try:
            cfg = load_config(config_file)
            project_name = cfg.project_file.name
            assembly_name = cfg.effective_assembly_name()
            version_str = cfg.version
        except Exception:
            pass

    if not project_name:
        # Search for .csproj in current directory
        candidates = sorted(
            p.name
            for p in root.rglob("*.csproj")
            if not {part.lower() for part in p.parts}.intersection(
                {"bin", "obj", "build", "build-exe", "dist", "dist-exe", ".venv"}
            )
        )
        if candidates:
            project_name = candidates[0] if len(candidates) == 1 else f"{candidates[0]} (+{len(candidates)-1} more)"

    installer = find_simpl_sharp_installer()
    installed = is_simpl_sharp_installed()

    return {
        "root": str(root),
        "config_exists": config_exists,
        "config_name": "clz-builder.json",
        "project_name": project_name,
        "assembly_name": assembly_name,
        "version_str": version_str,
        "simpl_installed": installed,
        "simpl_installer": installer.name if installer else None,
    }


def _render_header(info: dict[str, Any]) -> None:
    """Print the interactive terminal header."""
    print("=" * 76)
    print(f"      Crestron 3-Series / 4-Series CLZ Builder (v{__version__})")
    print("                    Interactive Console Terminal")
    print("=" * 76)
    print(f"  Working Folder : {info['root']}")

    cfg_status = "[FOUND]" if info["config_exists"] else "[NOT CONFIGURED]"
    if info["assembly_name"]:
        cfg_status += f" (Assembly: {info['assembly_name']} v{info['version_str']})"
    print(f"  Configuration  : {info['config_name']} {cfg_status}")

    proj = info["project_name"] or "None detected"
    print(f"  C# Project     : {proj}")

    if info["simpl_installed"]:
        sdk_status = "[INSTALLED]"
    elif info["simpl_installer"]:
        sdk_status = f"[NOT INSTALLED - Installer Found: {info['simpl_installer']}]"
    else:
        sdk_status = "[NOT INSTALLED - Missing Installer]"
    print(f"  SIMPL# SDK     : {sdk_status}")
    print("-" * 76)


def _render_menu(is_ready: bool = False) -> None:
    """Print the numbered menu options."""
    if is_ready:
        print("  [1] Quick Build / Recompile  <-- [DEFAULT: Press Enter]")
        print("      Increment version, compile C#, package CLZ and sign for Crestron Home.")
    else:
        print("  [1] Quick Build (Run)")
        print("      Increment version, compile C#, package CLZ and sign for Crestron Home.")
    print("")
    print("  [2] Guided Setup Wizard")
    print("      Configure project, SIMPL+ modules, check tools and generate lockfile.")
    print("")
    print("  [3] System Diagnostics (Doctor)")
    print("      Inspect compilers, SDK DLLs, and host toolchain readiness.")
    print("")
    print("  [4] Install Crestron SIMPL# Pro SDK")
    print("      Bypass Visual Studio 2008 requirement and auto-install SW-SIMPL-SHARP-PRO.")
    print("")
    print("  [5] Custom Build Options")
    print("      Select Debug/Release, target 3-Series or 4-Series, skip version bump, etc.")
    print("")
    print("  [6] Manage Toolchain Lockfile")
    print("      Generate or verify clz-builder.lock for deterministic builds.")
    print("")
    print("  [0] Exit")
    print("-" * 76)
    if is_ready:
        print("  >>> Everything is ready. Just press [Enter] to Recompile.")


def _action_quick_build() -> str:
    """Run one-click build loop with recompile on Enter.

    Returns:
        "menu" if user wants to return to main menu,
        "exit" if user wants to quit.
    """
    from .cli import _run_command

    while True:
        print("\n" + "=" * 76)
        print("--- Starting Quick Build (Recompile) ---")
        args = argparse.Namespace(
            config="clz-builder.json",
            project=None,
            modules=[],
            name=None,
            configuration="Release",
            targets=None,
            no_bump=False,
            verify_reproducible=False,
        )
        try:
            code = _run_command(args)
            if code == 0:
                print("\nBuild completed successfully!")
                dist_dir = Path.cwd() / "dist"
                if dist_dir.is_dir():
                    clz_files = sorted(
                        dist_dir.glob("*.clz"),
                        key=lambda p: p.stat().st_mtime,
                        reverse=True,
                    )
                    if clz_files:
                        print(f"Generated CLZ package: {clz_files[0]}")
            else:
                print(f"\nBuild finished with status code {code}.")
        except Exception as exc:
            print(f"\nBuild error: {exc}")

        print("-" * 76)
        try:
            next_step = input(
                "Press [Enter] to Recompile again, [M] for menu, or [0] to exit: "
            ).strip().lower()
        except (EOFError, KeyboardInterrupt):
            print("")
            return "menu"

        if next_step in ("m", "menu"):
            return "menu"
        if next_step in ("0", "q", "exit", "quit"):
            return "exit"
        # Any other key or empty Enter loops and recompiles!


def _action_guided_setup() -> None:
    """Run guided setup wizard."""
    from .cli import _setup_wizard

    print("\n--- Starting Guided Setup Wizard ---")
    args = argparse.Namespace(
        config=None,
        project=None,
        modules=[],
        name=None,
        force=False,
        non_interactive=False,
        auto_install=False,
    )
    try:
        _setup_wizard(args)
    except Exception as exc:
        print(f"\nSetup error: {exc}")


def _action_doctor() -> None:
    """Run diagnostics on host toolchain."""
    from .cli import _doctor, _print_checklist

    print("\n--- Running System Diagnostics ---")
    config_file = Path.cwd() / "clz-builder.json"

    if config_file.is_file():
        args = argparse.Namespace(config=str(config_file), as_json=False)
        try:
            _doctor(args)
        except Exception as exc:
            print(f"Diagnostics error: {exc}")
    else:
        print("No clz-builder.json found in current folder. Probing host toolchain directly...\n")
        try:
            with tempfile.TemporaryDirectory() as td:
                dummy_proj = Path(td) / "probe.csproj"
                dummy_proj.write_text("<Project />", encoding="utf-8")
                dummy_cfg = Path(td) / "clz-builder.json"
                import json
                dummy_cfg.write_text(
                    json.dumps(default_config("probe.csproj", ()), indent=2), encoding="utf-8"
                )
                from .config import load_config
                cfg = load_config(dummy_cfg)
                probes = probe_toolchain(cfg)
                _print_checklist(probes)
        except Exception as exc:
            print(f"Host probe error: {exc}")


def _action_install_prereqs() -> None:
    """Run prerequisite installer for SIMPL# Pro."""
    from .cli import _install_prereqs

    print("\n--- Install Crestron SIMPL# Pro SDK ---")
    args = argparse.Namespace(installer=None, yes=False, force=False)
    try:
        _install_prereqs(args)
    except Exception as exc:
        print(f"Installation error: {exc}")


def _action_custom_build() -> None:
    """Run a build with custom user-selected options."""
    from .cli import _run_command

    print("\n--- Custom Build Configuration ---")
    config_file = Path.cwd() / "clz-builder.json"
    if not config_file.is_file():
        print("Note: clz-builder.json will be automatically generated from your project.")

    # 1. Configuration: Release or Debug
    conf_choice = input("Build configuration [1] Release (default), [2] Debug: ").strip()
    configuration = "Debug" if conf_choice == "2" else "Release"

    # 2. Version increment
    bump_choice = input("Increment version for Crestron Home update? [Y/n] (default: Y): ").strip().lower()
    no_bump = bump_choice.startswith("n")

    # 3. Target platforms
    print("Target platforms:")
    print("  [1] All configured targets (3-Series & 4-Series) [default]")
    print("  [2] 3-Series only (series3)")
    print("  [3] 4-Series only (series4)")
    target_choice = input("Select targets [1-3] (default: 1): ").strip()
    targets = None
    if target_choice == "2":
        targets = "series3"
    elif target_choice == "3":
        targets = "series4"

    # 4. Verify reproducibility
    repro_choice = input("Verify reproducible build? [y/N] (default: N): ").strip().lower()
    verify_reproducible = repro_choice.startswith("y")

    print(f"\nRunning build: {configuration}, targets={targets or 'all'}, bump={not no_bump}...")
    args = argparse.Namespace(
        config="clz-builder.json",
        project=None,
        modules=[],
        name=None,
        configuration=configuration,
        targets=targets,
        no_bump=no_bump,
        verify_reproducible=verify_reproducible,
    )
    try:
        code = _run_command(args)
        if code == 0:
            print("\nCustom build completed successfully!")
            dist_dir = Path.cwd() / "dist"
            if dist_dir.is_dir():
                clz_files = list(dist_dir.glob("*.clz"))
                if clz_files:
                    print(f"Generated CLZ package: {clz_files[0]}")
        else:
            print(f"\nBuild finished with status code {code}.")
    except Exception as exc:
        print(f"\nBuild error: {exc}")


def _action_manage_lockfile() -> None:
    """Manage toolchain lockfile."""
    from .cli import _lock

    print("\n--- Toolchain Lockfile Management ---")
    config_file = Path.cwd() / "clz-builder.json"
    if not config_file.is_file():
        print("Error: clz-builder.json not found. Run Guided Setup first to configure your project.")
        return

    print("  [1] Generate / Update toolchain lockfile (lock)")
    print("  [2] Verify current toolchain against lockfile (lock --verify)")
    print("  [0] Return to main menu")
    choice = input("\nSelect an option [1-2, 0 to cancel]: ").strip()

    if choice == "1":
        try:
            _lock(argparse.Namespace(config="clz-builder.json", verify=False))
        except Exception as exc:
            print(f"Lock error: {exc}")
    elif choice == "2":
        try:
            _lock(argparse.Namespace(config="clz-builder.json", verify=True))
        except Exception as exc:
            print(f"Verification error: {exc}")


def run_interactive_menu() -> int:
    """Main interactive terminal loop."""
    while True:
        try:
            info = _get_environment_info()
            is_ready = bool(info["config_exists"] and info["simpl_installed"])

            _render_header(info)
            _render_menu(is_ready=is_ready)

            prompt_text = (
                "Select an option [0-6] or press [Enter] to Recompile: "
                if is_ready
                else "Select an option [0-6]: "
            )
            choice = input(prompt_text).strip()

            if is_ready and choice == "":
                choice = "1"

            if choice in ("0", "q", "exit", "quit"):
                print("\nExiting CLZ Builder. Goodbye!\n")
                return 0

            if choice == "1":
                result = _action_quick_build()
                if result == "exit":
                    print("\nExiting CLZ Builder. Goodbye!\n")
                    return 0
            elif choice == "2":
                _action_guided_setup()
                _pause()
            elif choice == "3":
                _action_doctor()
                _pause()
            elif choice == "4":
                _action_install_prereqs()
                _pause()
            elif choice == "5":
                _action_custom_build()
                _pause()
            elif choice == "6":
                _action_manage_lockfile()
                _pause()
            else:
                print(f"\nInvalid option '{choice}'. Please select a number from 0 to 6.")
                _pause()

        except KeyboardInterrupt:
            print("\n\nOperation cancelled. Exiting CLZ Builder.\n")
            return 0
        except EOFError:
            print("\nExiting CLZ Builder.\n")
            return 0
