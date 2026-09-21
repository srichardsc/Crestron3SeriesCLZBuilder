"""Detection, bypass, and installation helpers for Crestron SIMPL# Pro."""

from __future__ import annotations

import os
from pathlib import Path
import subprocess
import sys
from typing import Sequence

# Required SIMPL# SDK assemblies installed by SW-SIMPL-SHARP-PRO
SIMPL_SHARP_CORE_FILES = (
    "Crestron.Tools.SIMPLSharp.Services.dll",
    "CSharpCompiler.dll",
    "Ionic.Zip.dll",
    "Mono.Cecil.dll",
)

INSTALLER_PATTERNS = (
    "crestron_simpl_sharp_pro*.exe",
    "crestron_simpl_sharp*.exe",
    "*simpl_sharp*.exe",
    "*simpl#*.exe",
    "SW-SIMPL-SHARP*.exe",
)

VS2008_REG_SUBKEYS = (
    r"SOFTWARE\WOW6432Node\Microsoft\DevDiv\VS\Servicing\9.0",
    r"SOFTWARE\Microsoft\DevDiv\VS\Servicing\9.0",
)


def get_simpl_directory() -> Path:
    pf86 = os.environ.get("ProgramFiles(x86)") or os.environ.get("ProgramFiles") or r"C:\Program Files (x86)"
    return Path(pf86) / "Crestron" / "Simpl"


def is_simpl_sharp_installed() -> bool:
    """Check if the core SIMPL# SDK assemblies are already installed."""
    simpl_dir = get_simpl_directory()
    services_dll = simpl_dir / "Crestron.Tools.SIMPLSharp.Services.dll"
    compiler_dll = simpl_dir / "CSharpCompiler.dll"
    return services_dll.is_file() and compiler_dll.is_file()


def is_vs2008_sp1_bypass_installed() -> bool:
    """Check if the VS2008 SP1 servicing registry key is present."""
    if sys.platform != "win32":
        return False
    try:
        import winreg
    except ImportError:
        return False

    for subkey in VS2008_REG_SUBKEYS:
        for flags in (winreg.KEY_READ | getattr(winreg, "KEY_WOW64_32KEY", 0), winreg.KEY_READ):
            try:
                with winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, subkey, 0, flags) as key:
                    val, val_type = winreg.QueryValueEx(key, "SP")
                    if val_type in (winreg.REG_DWORD, winreg.REG_SZ) and int(val) >= 1:
                        return True
            except OSError:
                pass
    return False


def is_elevated() -> bool:
    """Check if the current process runs with Administrator privileges."""
    if sys.platform != "win32":
        return False
    try:
        import ctypes
        return bool(ctypes.windll.shell32.IsUserAnAdmin())
    except (AttributeError, OSError):
        return False


def apply_vs2008_sp1_bypass() -> tuple[bool, str]:
    """Apply the VS2008 SP1 registry bypass so the official installer does not abort."""
    if sys.platform != "win32":
        return False, "registry bypass is only applicable on Windows"

    if is_vs2008_sp1_bypass_installed():
        return True, "VS2008 SP1 bypass key is already present"

    # Try direct winreg write first (works if already elevated)
    try:
        import winreg
        for subkey in VS2008_REG_SUBKEYS:
            for flags in (winreg.KEY_WRITE | getattr(winreg, "KEY_WOW64_32KEY", 0), winreg.KEY_WRITE):
                try:
                    with winreg.CreateKeyEx(winreg.HKEY_LOCAL_MACHINE, subkey, 0, flags) as key:
                        winreg.SetValueEx(key, "SP", 0, winreg.REG_DWORD, 1)
                except OSError:
                    pass
        if is_vs2008_sp1_bypass_installed():
            return True, "VS2008 SP1 bypass key written directly"
    except Exception:
        pass

    # Elevation needed: run via PowerShell with RunAs
    ps_cmd = (
        'Start-Process powershell.exe -Verb RunAs -Wait -ArgumentList \'-NoProfile -NonInteractive -Command "'
        'New-Item -Path \\"HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\DevDiv\\VS\\Servicing\\9.0\\" -Force -ErrorAction SilentlyContinue; '
        'Set-ItemProperty -Path \\"HKLM:\\SOFTWARE\\WOW6432Node\\Microsoft\\DevDiv\\VS\\Servicing\\9.0\\" -Name \\"SP\\" -Value 1 -Type DWord -Force; '
        'New-Item -Path \\"HKLM:\\SOFTWARE\\Microsoft\\DevDiv\\VS\\Servicing\\9.0\\" -Force -ErrorAction SilentlyContinue; '
        'Set-ItemProperty -Path \\"HKLM:\\SOFTWARE\\Microsoft\\DevDiv\\VS\\Servicing\\9.0\\" -Name \\"SP\\" -Value 1 -Type DWord -Force;"\''
    )

    try:
        res = subprocess.run(["powershell.exe", "-NoProfile", "-Command", ps_cmd], capture_output=True, text=True, timeout=60, check=False)
        if res.returncode == 0 and is_vs2008_sp1_bypass_installed():
            return True, "VS2008 SP1 bypass key written via elevated PowerShell"
        return False, f"failed to apply VS2008 SP1 bypass key (exit code {res.returncode}): {res.stderr.strip()}"
    except Exception as exc:
        return False, f"error executing elevated bypass: {exc}"


def find_simpl_sharp_installer(search_paths: Sequence[Path] | None = None, include_defaults: bool = True) -> Path | None:
    """Find a Crestron SIMPL# Pro installer executable in local folders."""
    dirs_to_check: list[Path] = []

    if search_paths:
        for path in search_paths:
            p = path.resolve()
            if p.is_dir() and p not in dirs_to_check:
                dirs_to_check.append(p)

    if include_defaults or not search_paths:
        # 1. Application directory (where clz-builder.exe lives)
        app_dir = Path(sys.executable).parent.resolve()
        if app_dir.is_dir() and app_dir not in dirs_to_check:
            dirs_to_check.append(app_dir)

        # 2. Current working directory
        cwd = Path.cwd().resolve()
        if cwd.is_dir() and cwd not in dirs_to_check:
            dirs_to_check.append(cwd)

        # 3. .source/ subfolders
        for base in (cwd, app_dir):
            source_dir = (base / ".source").resolve()
            if source_dir.is_dir() and source_dir not in dirs_to_check:
                dirs_to_check.append(source_dir)

    # Search for matching installer binaries
    for directory in dirs_to_check:
        for pattern in INSTALLER_PATTERNS:
            for candidate in directory.glob(pattern):
                if candidate.is_file():
                    name_lower = candidate.name.lower()
                    # Do not match our own clz-builder binaries
                    if name_lower.startswith("clz-builder") or name_lower.startswith("test"):
                        continue
                    return candidate.resolve()

    return None


def install_simpl_sharp_pro(installer_path: Path, silent: bool = True) -> tuple[bool, str]:
    """Install SIMPL# Pro using the official installer after applying the VS2008 bypass."""
    installer = installer_path.resolve()
    if not installer.is_file():
        return False, f"installer file not found: {installer}"

    # 1. Ensure the VS2008 SP1 bypass key is present
    bypass_ok, bypass_msg = apply_vs2008_sp1_bypass()
    if not bypass_ok:
        return False, f"cannot proceed without VS2008 bypass: {bypass_msg}"

    # 2. Prepare installer flags
    flags = ["/VERYSILENT", "/SUPPRESSMSGBOXES", "/NORESTART"] if silent else []

    # 3. Launch installer (needs elevation to write to Program Files (x86))
    if is_elevated():
        try:
            result = subprocess.run([str(installer), *flags], capture_output=True, text=True, timeout=300, check=False)
            if result.returncode != 0:
                return False, f"installer exited with code {result.returncode}"
        except Exception as exc:
            return False, f"failed to run installer: {exc}"
    else:
        arg_string = " ".join(flags)
        ps_cmd = (
            f'$proc = Start-Process -FilePath "{installer}" '
            f'-ArgumentList "{arg_string}" -Verb RunAs -Wait -PassThru; '
            'exit $proc.ExitCode'
        )
        try:
            result = subprocess.run(
                ["powershell.exe", "-NoProfile", "-Command", ps_cmd],
                capture_output=True, text=True, timeout=300, check=False,
            )
            if result.returncode != 0:
                return False, f"elevated installer exited with code {result.returncode}"
        except Exception as exc:
            return False, f"failed to run elevated installer: {exc}"

    # 4. Verify installation result
    if is_simpl_sharp_installed():
        return True, "SIMPL# Pro installed successfully"

    # Even if exit code was 0, check if files arrived
    return False, "installer finished but SIMPL# assemblies were not found in standard location"
