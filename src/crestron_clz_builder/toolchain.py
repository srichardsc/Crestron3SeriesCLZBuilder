"""Discovery and locking for the installed Windows Crestron toolchain."""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import platform
import shutil
import subprocess
import re
import sys
from typing import Iterator, Mapping
import uuid
import zlib

from .config import ProjectConfig


OFFICIAL_SIGNER_THUMBPRINT = "258CCE9B7DA79C8D5C33431BDA2DD32CB64AEC7D"
LOCK_SCHEMA = 1


class ToolchainError(RuntimeError):
    """The required installed toolchain is unavailable or changed."""


# Human-readable metadata for every toolchain input, in the same order the
# resolver evaluates them. ``kind`` separates inputs a user can install from
# public downloads ("public") or Windows built-ins ("builtin") versus inputs
# that require a licensed Crestron installation ("licensed").
_ENTRY_SPECS: tuple[tuple[str, str, str, str, str], ...] = (
    # (name, human label, providing component, kind, actionable fix)
    ("msbuild", "MSBuild 17.x", "Visual Studio 2022 / Build Tools", "public",
     "run scripts\\Setup.ps1 -InstallBuildTools, or install VS2022 Community"),
    ("csc", ".NET Framework 3.5 csc.exe", "Windows feature .NET Framework 3.5", "public",
     "from an elevated shell run scripts\\Setup.ps1 -EnableNetFx3"),
    ("helperCsc", ".NET Framework 4 csc.exe (signer helper)", ".NET Framework 4.x (Windows built-in)", "builtin",
     "verify %WINDIR%\\Microsoft.NET\\Framework\\v4.0.30319\\csc.exe exists"),
    ("spluscc", "SPlusCC.exe (Crestron's SIMPL+ compiler)", "SIMPL Windows", "licensed",
     "install SIMPL Windows through your authorized Crestron dealer (docs/INSTALLATION.md)"),
    ("compiler", "CSharpCompiler.dll", "SIMPL# SDK", "licensed",
     "install the SIMPL# SDK through your authorized Crestron dealer (docs/INSTALLATION.md)"),
    ("services", "Crestron.Tools.SIMPLSharp.Services.dll", "SIMPL# SDK verification/signing service", "licensed",
     "install the SIMPL# SDK through your authorized Crestron dealer (docs/INSTALLATION.md)"),
    ("ionic", "Ionic.Zip.dll", "SDK CLZ processing dependency", "licensed",
     "installed together with SIMPL Windows / SIMPL# SDK"),
    ("cecil", "Mono.Cecil.dll", "SDK assembly processing dependency", "licensed",
     "installed together with SIMPL Windows / SIMPL# SDK"),
    ("cresdb", "Cresdb Programming data", "Cresdb Programming", "licensed",
     "install Cresdb Programming data through your authorized Crestron dealer"),
    ("cf", ".NET Compact Framework 3.5 reference assemblies", ".NET Compact Framework 3.5", "licensed",
     "obtain the supported CF 3.5 reference pack (docs/INSTALLATION.md); this tool never redistributes it"),
    ("references", "Required References", "Cresdb Programming data", "licensed",
     "installed together with Cresdb Programming data"),
    ("data", "Required Project Files", "Cresdb Programming data", "licensed",
     "installed together with Cresdb Programming data"),
    ("cf_mscorlib", "mscorlib.dll (Compact Framework)", ".NET Compact Framework 3.5", "licensed",
     "part of the CF 3.5 reference assemblies"),
    ("cf_system", "System.dll (Compact Framework)", ".NET Compact Framework 3.5", "licensed",
     "part of the CF 3.5 reference assemblies"),
    ("cf_system_core", "System.Core.dll (Compact Framework)", ".NET Compact Framework 3.5", "licensed",
     "part of the CF 3.5 reference assemblies"),
    ("cf_csc_rsp", "csc.rsp (Compact Framework build)", ".NET Framework 3.5", "public",
     "installed by the Windows .NET Framework 3.5 feature"),
    ("cf_common_targets", "Microsoft.Common.targets (CF build)", ".NET Framework 3.5", "public",
     "installed by the Windows .NET Framework 3.5 feature"),
    ("cf_csharp_targets", "Microsoft.CSharp.targets (CF build)", ".NET Framework 3.5", "public",
     "installed by the Windows .NET Framework 3.5 feature"),
    ("msbuild_rsp", "MSBuild.rsp", "Visual Studio 2022 / Build Tools", "public",
     "installed together with MSBuild"),
    ("helper_system", "System.dll (.NET Framework 4)", ".NET Framework 4.x (Windows built-in)", "builtin",
     "verify %WINDIR%\\Microsoft.NET\\Framework\\v4.0.30319 exists"),
    ("helper_reference", "SimplSharpHelperInterface.dll", "Cresdb Required References", "licensed",
     "installed together with Cresdb Programming data"),
    ("custom_attributes", "SimplSharpCustomAttributesInterface.dll", "Cresdb Required References", "licensed",
     "installed together with Cresdb Programming data"),
    ("data_file", "SimplSharpData.dat", "Cresdb Required Project Files", "licensed",
     "installed together with Cresdb Programming data"),
    ("data_signature", "SimplSharpData.dat.der (official data signature)", "Cresdb Required Project Files", "licensed",
     "installed together with Cresdb Programming data"),
)

_DIRECTORY_INPUTS = frozenset({"cresdb", "cf", "references", "data"})


@dataclass(frozen=True)
class ToolchainProbe:
    """Status of one named toolchain input on this host."""

    name: str
    label: str
    component: str
    kind: str
    fix: str
    expected_path: Path | None
    ok: bool

    @property
    def entry_type(self) -> str:
        return "directory" if self.name in _DIRECTORY_INPUTS else "file"


def _spec(name: str) -> tuple[str, str, str, str, str]:
    for spec in _ENTRY_SPECS:
        if spec[0] == name:
            return spec
    raise KeyError(name)


def _fail(message: str) -> None:
    raise ToolchainError(message)


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as stream:
            for chunk in iter(lambda: stream.read(1024 * 1024), b""):
                digest.update(chunk)
    except OSError as error:
        _fail(f"cannot hash toolchain input {path}: {error}")
    return digest.hexdigest()


def md5(path: Path) -> str:
    digest = hashlib.md5()
    with path.open("rb") as stream:
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def runtime_identity() -> dict[str, object]:
    executable = Path(sys.executable).resolve()
    if not executable.is_file():
        _fail(f"Python executable not found: {executable}")
    python = {
        "implementation": platform.python_implementation(),
        "version": platform.python_version(),
        "executableSha256": sha256(executable),
    }
    zlib_data = {
        "version": getattr(zlib, "ZLIB_VERSION", "unknown"),
        "runtimeVersion": getattr(zlib, "ZLIB_RUNTIME_VERSION", getattr(zlib, "ZLIB_VERSION", "unknown")),
    }
    zlib_path = Path(zlib.__file__).resolve() if getattr(zlib, "__file__", None) else None
    if zlib_path and zlib_path.is_file():
        zlib_data["moduleFile"] = zlib_path.name
        zlib_data["moduleFileSha256"] = sha256(zlib_path)
    else:
        # Some Python distributions link zlib into the interpreter. The
        # executable hash above then pins those bytes.
        zlib_data["embeddedInPython"] = True
    fingerprint = hashlib.sha256(
        json.dumps({"python": python, "zlib": zlib_data}, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return {"python": python, "zlib": zlib_data, "fingerprintSha256": fingerprint}


def _expand(value: str) -> str:
    value = os.path.expandvars(value)
    return re.sub(r"%([^%]+)%", lambda match: os.environ.get(match.group(1), match.group(0)), value)


def _environment_directory(name: str) -> Path:
    value = os.environ.get(name)
    if not value:
        _fail(f"required Windows environment variable is missing: {name}")
    return Path(value)


def _load_local_cache(config: ProjectConfig) -> dict[str, str]:
    path = config.resolved_local_cache_path
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    if not isinstance(payload, Mapping) or payload.get("schema") != 1:
        return {}
    paths = payload.get("paths")
    if not isinstance(paths, Mapping):
        return {}
    return {str(name): value for name, value in paths.items() if isinstance(value, str) and value.strip()}


def _validate_local_state_paths(config: ProjectConfig) -> None:
    root = config.root.resolve()
    cache = config.resolved_local_cache_path
    cache_parent = cache.parent
    try:
        cache_parent.resolve(strict=False).relative_to(root)
    except ValueError:
        _fail(f"local cache directory escapes the configuration root: {cache_parent}")
    if cache_parent.exists() and cache_parent.resolve() == root:
        _fail(f"local cache directory must be dedicated: {cache_parent}")
    lock = config.resolved_lock_path
    if lock.is_symlink():
        _fail(f"toolchain lock must not be a symlink: {lock}")


def _configured(config: ProjectConfig, cache: Mapping[str, str], name: str, fallback: Path) -> Path:
    # Explicit config wins. A cache path is only used while it still exists;
    # stale entries are discarded by normal discovery and replaced below.
    explicit = config.tool_paths.get(name)
    cached = cache.get(name) if not explicit else None
    raw = explicit or cached
    value = Path(_expand(raw)) if raw else fallback
    if cached and not value.exists():
        value = fallback
    if not value.is_absolute():
        value = config.root / value
    return value.resolve()


def _file(config: ProjectConfig, cache: Mapping[str, str], name: str, fallback: Path) -> Path:
    path = _configured(config, cache, name, fallback)
    if not path.is_file():
        _fail(f"required toolchain input not found ({name}): {path}")
    return path


def _directory(config: ProjectConfig, cache: Mapping[str, str], name: str, fallback: Path) -> Path:
    path = _configured(config, cache, name, fallback)
    if not path.is_dir():
        _fail(f"required toolchain directory not found ({name}): {path}")
    return path


def resolve_tools(config: ProjectConfig) -> dict[str, Path]:
    """Resolve every input used by the build, with no SDK files in the repo."""
    _validate_local_state_paths(config)
    cache = _load_local_cache(config)
    pf86 = _environment_directory("ProgramFiles(x86)")
    pf = _environment_directory("ProgramFiles")
    windir = _environment_directory("WINDIR")
    crestron = pf86 / "Crestron"
    simpl = crestron / "Simpl"
    cresdb_default = crestron / "Cresdb" / "Programming"
    cf_default = pf86 / "Microsoft.NET" / "SDK" / "CompactFramework" / "v3.5" / "WindowsCE"
    msbuild_defaults = (
        pf86 / "Microsoft Visual Studio" / "2022" / "Community" / "MSBuild" / "Current" / "Bin" / "MSBuild.exe",
        pf86 / "Microsoft Visual Studio" / "2022" / "BuildTools" / "MSBuild" / "Current" / "Bin" / "MSBuild.exe",
        pf / "Microsoft Visual Studio" / "2022" / "Community" / "MSBuild" / "Current" / "Bin" / "MSBuild.exe",
        pf / "Microsoft Visual Studio" / "2022" / "BuildTools" / "MSBuild" / "Current" / "Bin" / "MSBuild.exe",
    )
    vswhere_candidates = (
        pf86 / "Microsoft Visual Studio" / "Installer" / "vswhere.exe",
        pf / "Microsoft Visual Studio" / "Installer" / "vswhere.exe",
    )
    for vswhere in vswhere_candidates:
        if vswhere.is_file():
            try:
                result = subprocess.run(
                    [str(vswhere), "-latest", "-products", "*", "-requires", "Microsoft.Component.MSBuild", "-find", r"MSBuild\**\Bin\MSBuild.exe"],
                    capture_output=True, text=True, timeout=10, check=False,
                )
                msbuild_found = [Path(line.strip()) for line in result.stdout.splitlines() if line.strip()]
                msbuild_defaults = tuple(msbuild_found) + msbuild_defaults
            except (OSError, subprocess.SubprocessError):
                pass
            break
    path_msbuild = shutil.which("MSBuild.exe") or shutil.which("msbuild")
    if path_msbuild:
        msbuild_defaults = (Path(path_msbuild),) + msbuild_defaults
    env_msbuild = os.environ.get("CLZ_BUILDER_MSBUILD")
    if env_msbuild:
        msbuild_defaults = (Path(_expand(env_msbuild)),) + msbuild_defaults
    configured_msbuild = config.tool_paths.get("msbuild") or cache.get("msbuild")
    msbuild = _file(config, cache, "msbuild", next((candidate for candidate in msbuild_defaults if candidate.is_file()), msbuild_defaults[0])) if configured_msbuild else next((candidate.resolve() for candidate in msbuild_defaults if candidate.is_file()), None)
    if msbuild is None:
        _fail("required toolchain input not found (msbuild): install VS2022 MSBuild or set toolchain.paths.msbuild")
    tools: dict[str, Path] = {
        "msbuild": msbuild,
        "csc": _file(config, cache, "csc", windir / "Microsoft.NET" / "Framework" / "v3.5" / "csc.exe"),
        "helperCsc": _file(config, cache, "helperCsc", windir / "Microsoft.NET" / "Framework" / "v4.0.30319" / "csc.exe"),
        "spluscc": _file(config, cache, "spluscc", Path(shutil.which("SPlusCC.exe") or (simpl / "SPlusCC.exe"))),
        "compiler": _file(config, cache, "compiler", simpl / "CSharpCompiler.dll"),
        "services": _file(config, cache, "services", simpl / "Crestron.Tools.SIMPLSharp.Services.dll"),
        "ionic": _file(config, cache, "ionic", simpl / "Ionic.Zip.dll"),
        "cecil": _file(config, cache, "cecil", simpl / "Mono.Cecil.dll"),
        "cresdb": _directory(config, cache, "cresdb", cresdb_default),
        "cf": _directory(config, cache, "cf", cf_default),
    }
    references_default = tools["cresdb"] / "Libraries" / "Required References"
    data_default = tools["cresdb"] / "Libraries" / "Required Project Files"
    tools["references"] = _directory(config, cache, "references", references_default)
    tools["data"] = _directory(config, cache, "data", data_default)
    required = {
        "cf_mscorlib": _configured(config, cache, "cf_mscorlib", tools["cf"] / "mscorlib.dll"),
        "cf_system": _configured(config, cache, "cf_system", tools["cf"] / "System.dll"),
        "cf_system_core": _configured(config, cache, "cf_system_core", tools["cf"] / "System.Core.dll"),
        "cf_csc_rsp": _configured(config, cache, "cf_csc_rsp", windir / "Microsoft.NET" / "Framework" / "v3.5" / "csc.rsp"),
        "cf_common_targets": _configured(config, cache, "cf_common_targets", windir / "Microsoft.NET" / "Framework" / "v3.5" / "Microsoft.Common.targets"),
        "cf_csharp_targets": _configured(config, cache, "cf_csharp_targets", windir / "Microsoft.NET" / "Framework" / "v3.5" / "Microsoft.CSharp.targets"),
        "msbuild_rsp": _configured(config, cache, "msbuild_rsp", tools["msbuild"].parent / "MSBuild.rsp"),
        "helper_system": _configured(config, cache, "helper_system", tools["helperCsc"].parent / "System.dll"),
        "helper_reference": _configured(config, cache, "helper_reference", tools["references"] / "SimplSharpHelperInterface.dll"),
        "custom_attributes": _configured(config, cache, "custom_attributes", tools["references"] / "SimplSharpCustomAttributesInterface.dll"),
        "data_file": _configured(config, cache, "data_file", tools["data"] / "SimplSharpData.dat"),
        "data_signature": _configured(config, cache, "data_signature", tools["data"] / "SimplSharpData.dat.der"),
    }
    for name, path in required.items():
        if not path.is_file():
            _fail(f"required toolchain input not found ({name}): {path}")
        tools[name] = path.resolve()
    resolved = {name: path.resolve() for name, path in tools.items()}
    cache_path = config.resolved_local_cache_path
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    temporary = cache_path.with_name(f"{cache_path.name}.tmp-{uuid.uuid4().hex}")
    try:
        temporary.write_text(json.dumps({"schema": 1, "paths": {name: str(path) for name, path in sorted(resolved.items())}}, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        os.replace(str(temporary), str(cache_path))
    except OSError as error:
        try:
            temporary.unlink()
        except OSError:
            pass
        _fail(f"cannot persist local toolchain cache {cache_path}: {error}")
    return resolved


def probe_toolchain(config: ProjectConfig) -> list[ToolchainProbe]:
    """Report the status of every toolchain input without raising.

    ``resolve_tools`` stops at the first missing input; this probe answers
    every input independently so a user can see the full checklist of what is
    installed and what is missing on this host. Discovery reuses the same
    default-path logic as the resolver; when an input cannot be located at
    all (for example a required environment variable is absent) its expected
    path is reported as ``None``.
    """
    probes: list[ToolchainProbe] = []
    try:
        tools = resolve_tools(config)
        for spec_name, label, component, kind, fix in _ENTRY_SPECS:
            path = tools.get(spec_name)
            exists = path is not None and (path.is_dir() if spec_name in _DIRECTORY_INPUTS else path.is_file())
            probes.append(ToolchainProbe(spec_name, label, component, kind, fix, path, exists))
        return probes
    except ToolchainError:
        pass
    # Full discovery failed; answer each input independently so the checklist
    # still shows what IS installed and what is missing.
    cache = _load_local_cache(config)
    pf86_value, pf_value, windir_value = (os.environ.get(name) for name in ("ProgramFiles(x86)", "ProgramFiles", "WINDIR"))
    if not pf86_value or not pf_value or not windir_value:
        missing_variable = next(
            name
            for name, value in (("ProgramFiles(x86)", pf86_value), ("ProgramFiles", pf_value), ("WINDIR", windir_value))
            if not value
        )
        message = f"required Windows environment variable is missing: {missing_variable}"
        return [
            ToolchainProbe(spec[0], spec[1], spec[2], spec[3], f"{spec[4]} ({message})", None, False)
            for spec in _ENTRY_SPECS
        ]
    pf86, pf, windir = Path(pf86_value), Path(pf_value), Path(windir_value)
    crestron = pf86 / "Crestron"
    simpl = crestron / "Simpl"
    cresdb_default = crestron / "Cresdb" / "Programming"
    cf_default = pf86 / "Microsoft.NET" / "SDK" / "CompactFramework" / "v3.5" / "WindowsCE"

    def configured_or_cached(name: str) -> Path | None:
        explicit = config.tool_paths.get(name)
        cached = None if explicit else cache.get(name)
        raw = explicit or cached
        if not raw:
            return None
        value = Path(_expand(raw))
        if cached and not value.exists():
            return None
        if not value.is_absolute():
            value = config.root / value
        return value

    def default_for(name: str) -> Path | None:
        if name == "msbuild":
            candidates: list[Path] = []
            env_msbuild = os.environ.get("CLZ_BUILDER_MSBUILD")
            if env_msbuild:
                candidates.append(Path(_expand(env_msbuild)))
            which_msbuild = shutil.which("MSBuild.exe") or shutil.which("msbuild")
            if which_msbuild:
                candidates.append(Path(which_msbuild))
            vswhere_candidates = (
                pf86 / "Microsoft Visual Studio" / "Installer" / "vswhere.exe",
                pf / "Microsoft Visual Studio" / "Installer" / "vswhere.exe",
            )
            vswhere = next((entry for entry in vswhere_candidates if entry.is_file()), None)
            if vswhere is not None:
                try:
                    result = subprocess.run(
                        [str(vswhere), "-latest", "-products", "*", "-requires", "Microsoft.Component.MSBuild", "-find", r"MSBuild\**\Bin\MSBuild.exe"],
                        capture_output=True, text=True, timeout=10, check=False,
                    )
                    candidates.extend(Path(line.strip()) for line in result.stdout.splitlines() if line.strip())
                except (OSError, subprocess.SubprocessError):
                    pass
            for edition in ("Community", "BuildTools"):
                for base in (pf86, pf):
                    candidates.append(base / "Microsoft Visual Studio" / "2022" / edition / "MSBuild" / "Current" / "Bin" / "MSBuild.exe")
            found = next((candidate for candidate in candidates if candidate.is_file()), None)
            return found.resolve() if found else next((candidate for candidate in candidates if str(candidate)), candidates[-1])
        if name == "csc":
            return windir / "Microsoft.NET" / "Framework" / "v3.5" / "csc.exe"
        if name == "helperCsc":
            return windir / "Microsoft.NET" / "Framework" / "v4.0.30319" / "csc.exe"
        if name == "spluscc":
            which_spluscc = shutil.which("SPlusCC.exe")
            return Path(which_spluscc) if which_spluscc else simpl / "SPlusCC.exe"
        if name == "compiler":
            return simpl / "CSharpCompiler.dll"
        if name == "services":
            return simpl / "Crestron.Tools.SIMPLSharp.Services.dll"
        if name == "ionic":
            return simpl / "Ionic.Zip.dll"
        if name == "cecil":
            return simpl / "Mono.Cecil.dll"
        if name == "cresdb":
            return cresdb_default
        if name == "cf":
            return cf_default
        references_default = cresdb_default / "Libraries" / "Required References"
        data_default = cresdb_default / "Libraries" / "Required Project Files"
        if name == "references":
            return references_default
        if name == "data":
            return data_default
        if name == "cf_mscorlib":
            return cf_default / "mscorlib.dll"
        if name == "cf_system":
            return cf_default / "System.dll"
        if name == "cf_system_core":
            return cf_default / "System.Core.dll"
        if name == "cf_csc_rsp":
            return windir / "Microsoft.NET" / "Framework" / "v3.5" / "csc.rsp"
        if name == "cf_common_targets":
            return windir / "Microsoft.NET" / "Framework" / "v3.5" / "Microsoft.Common.targets"
        if name == "cf_csharp_targets":
            return windir / "Microsoft.NET" / "Framework" / "v3.5" / "Microsoft.CSharp.targets"
        msbuild_path = configured_or_cached("msbuild") or default_for("msbuild")
        if name == "msbuild_rsp":
            return msbuild_path.parent / "MSBuild.rsp"
        if name == "helper_system":
            helper_csc = configured_or_cached("helperCsc")
            base = helper_csc.parent if helper_csc else windir / "Microsoft.NET" / "Framework" / "v4.0.30319"
            return base / "System.dll"
        references_path = configured_or_cached("references") or (cache.get("references") and Path(cache["references"])) or references_default  # type: ignore[operator]
        data_path = configured_or_cached("data") or (cache.get("data") and Path(cache["data"])) or data_default  # type: ignore[operator]
        if name == "helper_reference":
            return references_path / "SimplSharpHelperInterface.dll"
        if name == "custom_attributes":
            return references_path / "SimplSharpCustomAttributesInterface.dll"
        if name == "data_file":
            return data_path / "SimplSharpData.dat"
        if name == "data_signature":
            return data_path / "SimplSharpData.dat.der"
        raise KeyError(name)

    results: list[ToolchainProbe] = []
    for spec in _ENTRY_SPECS:
        name = spec[0]
        expected = configured_or_cached(name) or default_for(name)
        exists = expected is not None and (expected.is_dir() if name in _DIRECTORY_INPUTS else expected.is_file())
        results.append(ToolchainProbe(name, spec[1], spec[2], spec[3], spec[4], expected if isinstance(expected, Path) else None, exists))
    return results


LOCK_INPUT_NAMES = (
    "msbuild", "csc", "helperCsc", "spluscc", "compiler", "services", "ionic", "cecil",
    "cf_mscorlib", "cf_system", "cf_system_core", "cf_csc_rsp", "cf_common_targets",
    "cf_csharp_targets", "msbuild_rsp", "helper_system", "helper_reference", "custom_attributes",
    "data_file", "data_signature",
)


def lock_inputs(tools: Mapping[str, Path]) -> dict[str, dict[str, object]]:
    return {
        name: {"file": tools[name].name, "sha256": sha256(tools[name]), "size": tools[name].stat().st_size}
        for name in LOCK_INPUT_NAMES
    }


def write_lock(config: ProjectConfig, tools: Mapping[str, Path]) -> Path:
    path = config.resolved_lock_path
    _validate_local_state_paths(config)
    payload = {
        "schema": LOCK_SCHEMA,
        "signerThumbprint": OFFICIAL_SIGNER_THUMBPRINT,
        "runtime": runtime_identity(),
        "inputs": lock_inputs(tools),
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f"{path.name}.tmp-{uuid.uuid4().hex}")
    try:
        temporary.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8", newline="\n")
        os.replace(str(temporary), str(path))
    except OSError as error:
        try:
            temporary.unlink()
        except OSError:
            pass
        _fail(f"cannot persist toolchain lock {path}: {error}")
    return path


def verify_lock(config: ProjectConfig, tools: Mapping[str, Path]) -> None:
    path = config.resolved_lock_path
    _validate_local_state_paths(config)
    if not path.is_file():
        _fail(f"toolchain lock missing: {path}; run `lock --config {config.path.name}` deliberately")
    try:
        expected = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        _fail(f"cannot read toolchain lock {path}: {error}")
    if expected.get("schema") != LOCK_SCHEMA:
        _fail(f"unsupported toolchain lock schema in {path}")
    if expected.get("signerThumbprint", "").upper() != OFFICIAL_SIGNER_THUMBPRINT:
        _fail(f"toolchain lock signer mismatch: {path}")
    if expected.get("runtime", {}).get("fingerprintSha256") != runtime_identity()["fingerprintSha256"]:
        _fail("Python/zlib runtime changed; run `lock` deliberately to update the lock")
    actual = lock_inputs(tools)
    for name, values in actual.items():
        if expected.get("inputs", {}).get(name) != values:
            _fail(f"toolchain input changed ({name}); run `lock` deliberately to update the lock")


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _process_start_token(pid: int) -> str | None:
    """Return an OS process-start identity to detect PID reuse."""
    if pid <= 0:
        return None
    if os.name == "nt":
        try:
            import ctypes
            from ctypes import wintypes
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            kernel32.OpenProcess.argtypes = (wintypes.DWORD, wintypes.BOOL, wintypes.DWORD)
            kernel32.OpenProcess.restype = wintypes.HANDLE
            kernel32.GetProcessTimes.argtypes = (
                wintypes.HANDLE,
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
                ctypes.POINTER(wintypes.FILETIME),
            )
            kernel32.GetProcessTimes.restype = wintypes.BOOL
            kernel32.CloseHandle.argtypes = (wintypes.HANDLE,)
            kernel32.CloseHandle.restype = wintypes.BOOL
            handle = kernel32.OpenProcess(0x1000, False, pid)
            if not handle:
                return None
            creation, exit_time = wintypes.FILETIME(), wintypes.FILETIME()
            kernel_time, user_time = wintypes.FILETIME(), wintypes.FILETIME()
            try:
                if not kernel32.GetProcessTimes(handle, ctypes.byref(creation), ctypes.byref(exit_time), ctypes.byref(kernel_time), ctypes.byref(user_time)):
                    return None
                return str((creation.dwHighDateTime << 32) | creation.dwLowDateTime)
            finally:
                kernel32.CloseHandle(handle)
        except (OSError, AttributeError, ImportError):
            return None
    try:
        text = Path(f"/proc/{pid}/stat").read_text(encoding="ascii")
        closing = text.rfind(")")
        if closing < 0:
            return None
        return text[closing + 2 :].split()[19]
    except (OSError, IndexError, UnicodeError):
        return None


def _claim_lock(lock: Path) -> Path | None:
    recovery = lock.with_name(f"{lock.name}.recovery-{uuid.uuid4().hex}")
    try:
        os.replace(str(lock), str(recovery))
    except FileNotFoundError:
        return None
    except OSError as error:
        _fail(f"could not atomically claim stale build lock {lock}: {error}")
    return recovery


@contextmanager
def build_lock(config: ProjectConfig, recover: bool = False) -> Iterator[None]:
    """Serialize builds and fail closed when an unreadable lock is present."""
    lock = config.resolved_build_dir / ".clz-builder.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    owner = {"pid": os.getpid(), "token": uuid.uuid4().hex, "startedUtc": datetime.now(timezone.utc).isoformat(), "script": str(Path(__file__).resolve())}
    process_token = _process_start_token(owner["pid"])
    if process_token is not None:
        owner["processStartToken"] = process_token
    text = json.dumps(owner, sort_keys=True, separators=(",", ":"))
    while True:
        try:
            descriptor = os.open(str(lock), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            break
        except FileExistsError:
            try:
                existing_text = lock.read_text(encoding="utf-8")
                current = json.loads(existing_text)
                pid = int(current.get("pid", 0))
            except (OSError, ValueError, TypeError, json.JSONDecodeError):
                if not recover:
                    _fail(f"build lock unreadable: {lock}; verify no build runs, then use --recover-lock")
                recovery = _claim_lock(lock)
                if recovery is None:
                    continue
                try:
                    recovery.unlink()
                except OSError as unlink_error:
                    _fail(f"could not recover unreadable build lock {lock}: {unlink_error}")
                continue
            if _pid_alive(pid):
                existing_token = current.get("processStartToken")
                current_token = _process_start_token(pid)
                if not (existing_token and current_token and str(existing_token) != str(current_token)):
                    _fail(f"another build holds {lock} (pid {pid}); do not run concurrently")
            recovery = _claim_lock(lock)
            if recovery is None:
                continue
            try:
                claimed_text = recovery.read_text(encoding="utf-8")
            except OSError as error:
                _fail(f"stale build lock became unreadable while claimed: {recovery}: {error}")
            if claimed_text != existing_text:
                _fail(f"build lock changed while being recovered; inspect {recovery}")
            try:
                recovery.unlink()
            except OSError as error:
                _fail(f"recovered build lock could not be removed: {recovery}: {error}")
    try:
        os.write(descriptor, text.encode("utf-8"))
        os.fsync(descriptor)
        yield
    finally:
        os.close(descriptor)
        try:
            current = json.loads(lock.read_text(encoding="utf-8"))
            if current.get("token") == owner["token"]:
                lock.unlink()
        except (FileNotFoundError, OSError, json.JSONDecodeError):
            pass
