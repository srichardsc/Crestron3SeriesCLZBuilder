"""Versioned project configuration for the CLZ builder.

The configuration deliberately contains paths and public metadata only.  It
never contains a signing key: signing is delegated to the installed Crestron
SIMPL# service.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from string import Formatter
import xml.etree.ElementTree as ET
from typing import Any, Mapping


class ConfigError(ValueError):
    """A project configuration is missing or has an invalid value."""


SUPPORTED_SCHEMA = 1
TARGETS = ("series3", "series4")
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}
TOOL_NAMES = (
    "msbuild",
    "csc",
    "helperCsc",
    "spluscc",
    "compiler",
    "services",
    "ionic",
    "cecil",
    "cresdb",
    "references",
    "data",
    "cf",
    "cf_mscorlib",
    "cf_system",
    "cf_system_core",
    "cf_csc_rsp",
    "cf_common_targets",
    "cf_csharp_targets",
    "msbuild_rsp",
    "helper_system",
    "helper_reference",
    "custom_attributes",
    "data_file",
    "data_signature",
)


def _string(value: Any, label: str, *, required: bool = True) -> str | None:
    if value is None and not required:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ConfigError(f"{label} must be a non-empty string")
    return value.strip()


def _validate_assembly_name(value: str, label: str = "assembly.name") -> str:
    invalid = any(ord(character) < 32 or character in '<>:"/\\|?*' for character in value)
    reserved = value.split(".", 1)[0].upper() in WINDOWS_RESERVED_NAMES
    if Path(value).name != value or invalid or value.endswith((" ", ".")) or reserved:
        raise ConfigError(f"{label} must be a valid, non-reserved Windows filename stem")
    return value


def _relative_path(value: Any, label: str) -> str:
    text = _string(value, label)
    path = Path(text)
    if path.is_absolute():
        raise ConfigError(f"{label} must be relative to the project root: {text}")
    if any(part == ".." for part in path.parts):
        raise ConfigError(f"{label} cannot escape the project root: {text}")
    return text


def _output_path(value: Any, label: str) -> str:
    text = _relative_path(value, label)
    if Path(text) in (Path(""), Path(".")):
        raise ConfigError(f"{label} must name a dedicated output directory")
    first = Path(text).parts[0].lower()
    if first == ".clz-builder" or Path(text).name.lower() == "toolchain.lock.json":
        raise ConfigError(f"{label} collides with reserved builder state")
    return text


def _path_list(value: Any, label: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ConfigError(f"{label} must be an array")
    result: list[str] = []
    for index, item in enumerate(value):
        if isinstance(item, str):
            raw = item
        elif isinstance(item, Mapping):
            raw = item.get("path")
        else:
            raw = None
        result.append(_relative_path(raw, f"{label}[{index}].path"))
    if len(set(Path(item).name.lower() for item in result)) != len(result):
        raise ConfigError(f"{label} contains duplicate package filenames")
    return tuple(result)


@dataclass(frozen=True)
class Module:
    source: str

    @property
    def filename(self) -> str:
        return Path(self.source).name

    @property
    def header_filename(self) -> str:
        return f"{Path(self.source).stem}.ush"


@dataclass(frozen=True)
class ProjectConfig:
    path: Path
    root: Path
    project: str
    assembly_name: str | None
    assembly_output: str
    version: str
    minimum_firmware: str
    modules: tuple[Module, ...]
    targets: tuple[str, ...]
    dependencies: tuple[str, ...]
    resources: tuple[str, ...]
    metadata: Mapping[str, str]
    tool_paths: Mapping[str, str]
    build_dir: str
    dist_dir: str

    @property
    def project_file(self) -> Path:
        return self.root / self.project

    @property
    def resolved_lock_path(self) -> Path:
        return self.root / "toolchain.lock.json"

    @property
    def resolved_local_cache_path(self) -> Path:
        return self.root / ".clz-builder" / "toolchain.local.json"

    @property
    def resolved_build_dir(self) -> Path:
        return self.root / self.build_dir

    @property
    def resolved_dist_dir(self) -> Path:
        return self.root / self.dist_dir

    @property
    def resolved_modules(self) -> tuple[Path, ...]:
        return tuple(self.root / module.source for module in self.modules)

    @property
    def resolved_dependencies(self) -> tuple[Path, ...]:
        return tuple(self.root / path for path in self.dependencies)

    @property
    def resolved_resources(self) -> tuple[Path, ...]:
        return tuple(self.root / path for path in self.resources)

    def effective_assembly_name(self) -> str:
        if self.assembly_name:
            return self.assembly_name
        try:
            tree = ET.parse(self.project_file)
        except (OSError, ET.ParseError) as error:
            raise ConfigError(f"cannot infer assembly name from {self.project_file}: {error}") from error
        values = [
            element.text.strip()
            for element in tree.getroot().iter()
            if element.tag.rsplit("}", 1)[-1] == "AssemblyName" and element.text and element.text.strip()
        ]
        if not values:
            raise ConfigError("assembly.name is required when the project has no AssemblyName")
        return _validate_assembly_name(values[0], "project AssemblyName")


def _parse_modules(value: Any) -> tuple[Module, ...]:
    if value is None:
        return ()
    if not isinstance(value, list):
        raise ConfigError("modules must be an array when provided")
    modules = []
    for index, item in enumerate(value):
        source = item if isinstance(item, str) else item.get("source") if isinstance(item, Mapping) else None
        source = _relative_path(source, f"modules[{index}].source")
        if Path(source).suffix.lower() != ".usp":
            raise ConfigError(f"modules[{index}].source must have .usp extension")
        modules.append(Module(source))
    names = [module.filename.lower() for module in modules]
    if len(set(names)) != len(names):
        raise ConfigError("modules contain duplicate filenames")
    return tuple(modules)


def _metadata(raw: Any, assembly_name: str | None) -> dict[str, str]:
    if raw is None:
        raw = {}
    if not isinstance(raw, Mapping):
        raise ConfigError("package.metadata must be an object")
    defaults = {
        "friendlyName": assembly_name or "SIMPL# package",
        "systemName": assembly_name or "SIMPLSharpPackage",
        "entryPoint": assembly_name or "SIMPLSharpPackage",
        "programTool": "SIMPL# Plugin",
        "designToolId": "5",
        "programToolId": "5",
        "archiveName": "",
        "programmerName": "",
        "compiledOn": "01-01-2026 00:00:00",
        "compilerRev": "1.0.0.0",
        "pluginVersion": "Crestron.SIMPLSharp, Version=2.0.52.0, Culture=neutral, PublicKeyToken=812d080f93e2de10",
    }
    result: dict[str, str] = {}
    for key, default in defaults.items():
        value = raw.get(key, default)
        if isinstance(value, bool) or not isinstance(value, (str, int, float)):
            raise ConfigError(f"package.metadata.{key} must be a string or number")
        result[key] = str(value)
    return result


def load_config(path: Path) -> ProjectConfig:
    path = path.resolve()
    if path.name.lower() == "toolchain.lock.json" or path.parent.name.lower() == ".clz-builder":
        raise ConfigError("configuration path collides with reserved builder state")
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as error:
        raise ConfigError(f"configuration not found: {path}") from error
    except (OSError, json.JSONDecodeError) as error:
        raise ConfigError(f"cannot read configuration {path}: {error}") from error
    if not isinstance(raw, Mapping):
        raise ConfigError("configuration root must be an object")
    schema = raw.get("schema")
    if schema != SUPPORTED_SCHEMA:
        raise ConfigError(f"unsupported configuration schema {schema!r}; expected {SUPPORTED_SCHEMA}")
    root = path.parent
    assembly = raw.get("assembly")
    if not isinstance(assembly, Mapping):
        raise ConfigError("assembly must be an object")
    project = _relative_path(assembly.get("project"), "assembly.project")
    if Path(project).suffix.lower() != ".csproj":
        raise ConfigError("assembly.project must have .csproj extension")
    name = assembly.get("name")
    name = _string(name, "assembly.name", required=False)
    if name:
        name = _validate_assembly_name(name)
    version = _string(assembly.get("version", "1.0.0.0"), "assembly.version")
    minimum_firmware = _string(assembly.get("minimumFirmware", "1.007.0017"), "assembly.minimumFirmware")
    assembly_output = _relative_path(assembly.get("output", "bin/{configuration}/{name}.dll"), "assembly.output")
    try:
        fields = []
        for _, field_name, format_spec, conversion in Formatter().parse(assembly_output):
            if field_name is None:
                continue
            if field_name not in {"configuration", "name", "version"} or format_spec or conversion:
                raise ConfigError(
                    "assembly.output supports only plain {configuration}, {name}, and {version} placeholders"
                )
            fields.append(field_name)
    except ValueError as error:
        raise ConfigError(f"assembly.output has invalid placeholder syntax: {error}") from error
    if "name" not in fields or not assembly_output.lower().endswith("{name}.dll"):
        raise ConfigError("assembly.output must end in {name}.dll")
    try:
        assembly_output.format(configuration="Release", name="Assembly", version=version)
    except (KeyError, ValueError) as error:
        raise ConfigError("assembly.output may use only {configuration}, {name}, and {version}") from error

    targets_raw = raw.get("targets", list(TARGETS))
    if not isinstance(targets_raw, list) or not targets_raw:
        raise ConfigError("targets must be a non-empty array")
    targets = tuple(dict.fromkeys(str(item).lower() for item in targets_raw))
    if any(target not in TARGETS for target in targets):
        raise ConfigError(f"targets must contain only {', '.join(TARGETS)}")

    package = raw.get("package", {})
    if not isinstance(package, Mapping):
        raise ConfigError("package must be an object")
    toolchain = raw.get("toolchain", {})
    if not isinstance(toolchain, Mapping):
        raise ConfigError("toolchain must be an object")
    unknown_toolchain = set(toolchain) - {"paths"}
    if unknown_toolchain:
        raise ConfigError(f"unknown toolchain key: {sorted(unknown_toolchain)[0]}")
    paths = toolchain.get("paths", {})
    if not isinstance(paths, Mapping):
        raise ConfigError("toolchain.paths must be an object")
    tool_paths: dict[str, str] = {}
    for key, value in paths.items():
        if key not in TOOL_NAMES:
            raise ConfigError(f"unknown toolchain.paths key: {key}")
        tool_paths[key] = _string(value, f"toolchain.paths.{key}")  # type: ignore[assignment]
    output = raw.get("output", {})
    if not isinstance(output, Mapping):
        raise ConfigError("output must be an object")
    build_dir = _output_path(output.get("build", "build"), "output.build")
    dist_dir = _output_path(output.get("dist", "dist"), "output.dist")
    build_path, dist_path = Path(build_dir), Path(dist_dir)
    if build_path == dist_path or build_path in dist_path.parents or dist_path in build_path.parents:
        raise ConfigError("output.build and output.dist must not overlap")
    root_resolved = root.resolve()
    for label, relative in (("output.build", build_dir), ("output.dist", dist_dir)):
        candidate = root / relative
        try:
            candidate.resolve(strict=False).relative_to(root_resolved)
        except ValueError as error:
            raise ConfigError(f"{label} escapes the configuration root through a symlink or junction") from error
    project_path = root / project
    module_paths = [root / module.source for module in _parse_modules(raw.get("modules"))]
    for label, relative in (("output.build", build_dir), ("output.dist", dist_dir)):
        output_path = root / relative
        for source in [project_path, *module_paths]:
            if output_path == source.parent or output_path in source.parents:
                raise ConfigError(f"{label} must not contain project source: {source}")
    return ProjectConfig(
        path=path,
        root=root,
        project=project,
        assembly_name=name,
        assembly_output=assembly_output,
        version=version,
        minimum_firmware=minimum_firmware,
        modules=tuple(Module(path.relative_to(root).as_posix()) for path in module_paths),
        targets=targets,
        dependencies=_path_list(package.get("dependencies", []), "package.dependencies"),
        resources=_path_list(package.get("resources", []), "package.resources"),
        metadata=_metadata(package.get("metadata"), name),
        tool_paths=tool_paths,
        build_dir=build_dir,
        dist_dir=dist_dir,
    )


def default_config(project: str, modules: list[str], *, name: str | None = None) -> dict[str, Any]:
    """Return a minimal, explicit schema-1 configuration for ``init``."""
    inferred = name or Path(project).stem
    return {
        "schema": SUPPORTED_SCHEMA,
        "assembly": {
            "project": project,
            "name": inferred,
            "version": "1.0.0.0",
            "minimumFirmware": "1.007.0017",
            "output": "bin/{configuration}/{name}.dll",
        },
        "modules": modules,
        "targets": list(TARGETS),
        "package": {
            "dependencies": [],
            "resources": [],
            "metadata": {"friendlyName": inferred, "systemName": inferred, "entryPoint": inferred},
        },
        "toolchain": {"paths": {}},
        "output": {"build": "build", "dist": "dist"},
    }
