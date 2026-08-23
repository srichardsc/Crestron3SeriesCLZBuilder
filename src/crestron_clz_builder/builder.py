"""Deterministic assembly, CLZ and SIMPL+ build pipeline."""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import html
import json
from pathlib import Path
import shutil
import struct
import subprocess
import sys
import uuid
import zipfile
import zlib
from typing import Iterable, Mapping, Sequence

from .config import ProjectConfig
from .toolchain import OFFICIAL_SIGNER_THUMBPRINT, ToolchainError, md5, resolve_tools, sha256, verify_lock


class BuildError(RuntimeError):
    """A build gate failed."""


@dataclass(frozen=True)
class BuildOptions:
    configuration: str = "Release"
    targets: tuple[str, ...] = ()
    verify_reproducible: bool = False
    publish: bool = True
    recover_lock: bool = False


def _fail(message: str) -> None:
    raise BuildError(message)


def _run(command: Sequence[object], *, cwd: Path) -> None:
    printable = " ".join(f'"{part}"' if " " in str(part) else str(part) for part in command)
    print(f"> {printable}", flush=True)
    try:
        completed = subprocess.run([str(part) for part in command], cwd=str(cwd))
    except OSError as error:
        _fail(f"cannot start command {printable}: {error}")
    if completed.returncode != 0:
        _fail(f"command failed ({completed.returncode}): {printable}")


def _remove(path: Path) -> None:
    if path.is_symlink() or path.is_file():
        path.unlink()
    elif path.is_dir():
        shutil.rmtree(path)


def _assert_file(path: Path, label: str) -> None:
    if not path.is_file():
        _fail(f"{label} missing: {path}")


def stable_mvid(config: ProjectConfig, lock_path: Path, assembly_name: str) -> str:
    digest = hashlib.sha256()
    material = [config.project_file]
    project_root = config.project_file.parent
    material.extend(
        sorted(
            path
            for path in project_root.rglob("*.cs")
            if not {part.lower() for part in path.parts}.intersection({"bin", "obj"})
        )
    )
    material.extend(config.resolved_modules)
    for path in material:
        _assert_file(path, "MVID input")
        try:
            relative = path.relative_to(config.root).as_posix()
        except ValueError:
            relative = path.name
        digest.update(relative.encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    try:
        lock = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        _fail(f"cannot read toolchain lock for MVID: {error}")
    semantic_config = {
        "schema": 1,
        "assembly": {
            "project": config.project,
            "name": assembly_name,
            "output": config.assembly_output,
            "version": config.version,
            "minimumFirmware": config.minimum_firmware,
        },
        "modules": [module.source for module in config.modules],
        "package": {
            "dependencies": list(config.dependencies),
            "resources": list(config.resources),
            "metadata": dict(sorted(config.metadata.items())),
        },
    }
    identity = {
        "schema": lock.get("schema"),
        "signerThumbprint": lock.get("signerThumbprint"),
        "runtime": lock.get("runtime", {}).get("fingerprintSha256"),
        "inputs": lock.get("inputs", {}),
        "config": semantic_config,
    }
    digest.update(b"toolchain.lock.identity\0")
    digest.update(json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8"))
    return str(uuid.UUID(bytes=digest.digest()[:16]))


def _ensure_signer(tools: Mapping[str, Path], build_root: Path) -> Path:
    signer_source = Path(__file__).with_name("Signer.cs")
    _assert_file(signer_source, "Signer.cs")
    helper_dir = build_root / "tools"
    helper_dir.mkdir(parents=True, exist_ok=True)
    helper = helper_dir / "Signer.exe"
    _run(
        [
            tools["helperCsc"], "/nologo", "/noconfig", "/target:exe", "/platform:x86",
            "/out:" + str(helper), "/r:" + str(tools["helper_system"]), "/r:" + str(tools["cecil"]),
            signer_source,
        ],
        cwd=signer_source.parent,
    )
    shutil.copy2(tools["cecil"], helper_dir / tools["cecil"].name)
    _assert_file(helper, "Signer helper")
    return helper


def _write_program_config(stage: Path, config: ProjectConfig, assembly_name: str) -> None:
    metadata = config.metadata
    def tag(name: str, value: str) -> str:
        return f"    <{name}>{html.escape(value, quote=False)}</{name}>"
    archive = "    <ArchiveName />" if not metadata["archiveName"] else tag("ArchiveName", metadata["archiveName"])
    text = "\n".join(
        [
            "<ProgramInfo>",
            "  <RequiredInfo>",
            tag("FriendlyName", metadata["friendlyName"]),
            tag("SystemName", metadata["systemName"]),
            tag("EntryPoint", metadata["entryPoint"]),
            tag("MinFirmwareVersion", config.minimum_firmware),
            tag("ProgramTool", metadata["programTool"]),
            tag("DesignToolId", metadata["designToolId"]),
            tag("ProgramToolId", metadata["programToolId"]),
            archive,
            "  </RequiredInfo>",
            "  <OptionalInfo>",
            tag("ProgrammerName", metadata["programmerName"]),
            tag("CompiledOn", metadata["compiledOn"]),
            tag("CompilerRev", metadata["compilerRev"]),
            "  </OptionalInfo>",
            "  <Plugin>",
            tag("Version", metadata["pluginVersion"]),
            "    <Include4.dat />",
            "  </Plugin>",
            "</ProgramInfo>",
            "",
        ]
    )
    (stage / f"{assembly_name}.config").write_bytes(text.replace("\n", "\r\n").encode("utf-8"))


def _manifest_info(main: Path, dependencies: Sequence[Path], resources: Sequence[Path], config: ProjectConfig, assembly_name: str) -> list[str]:
    lines = [f"MainAssembly={main.name}:{md5(main)}", f"MainAssemblyMinFirmwareVersion={config.minimum_firmware}"]
    for resource in resources:
        lines.append(f"MainAssemblyResource={resource.name}:{md5(resource)}")
    for dependency in dependencies:
        digest = md5(dependency)
        lines.extend([
            "ü",
            f"DependencySource={dependency.name}:{digest}",
            f"DependencyPath={assembly_name}.clz:{dependency.name}",
            f"DependencyMainAssembly={dependency.name}:{digest}",
        ])
    return lines


def _manifest_model(main: Path, dependencies: Sequence[Path], resources: Sequence[Path], config: ProjectConfig, assembly_name: str) -> dict[str, object]:
    dep_items: list[dict[str, object]] = []
    next_id = 3
    for dependency in dependencies:
        digest = md5(dependency)
        dep_items.append({
            "$id": str(next_id), "Filename": dependency.name, "Hash": digest, "Source": dependency.name,
            "SourceHash": digest, "Path": f"{assembly_name}.clz:{dependency.name}", "LocalPath": "",
            "Dependencies": [], "Resources": [],
        })
        next_id += 1
    resource_items: list[dict[str, object]] = []
    for resource in resources:
        resource_items.append({
            "$id": str(next_id), "Filename": resource.name, "Hash": md5(resource),
            "Source": f"{assembly_name}.clz", "Path": f"{assembly_name}.clz", "LocalPath": resource.name,
        })
        next_id += 1
    return {
        "$id": "1", "Name": f"{assembly_name}.clz",
        "MainAssembly": {
            "$id": "2", "Filename": main.name, "Version": config.version,
            "MinimumFirmware": config.minimum_firmware, "Hash": md5(main),
            "Source": f"{assembly_name}.clz", "Path": f"{assembly_name}.clz", "LocalPath": "",
            "Dependencies": dep_items, "Resources": resource_items,
        },
    }


def _deterministic_gzip(raw: bytes) -> bytes:
    compressor = zlib.compressobj(level=9, method=zlib.DEFLATED, wbits=-15)
    compressed = compressor.compress(raw) + compressor.flush()
    return b"\x1f\x8b\x08\x00\x00\x00\x00\x00\x02\xff" + compressed + struct.pack("<II", zlib.crc32(raw) & 0xFFFFFFFF, len(raw) & 0xFFFFFFFF)


def _write_manifests(stage: Path, main: Path, dependencies: Sequence[Path], resources: Sequence[Path], config: ProjectConfig, assembly_name: str) -> None:
    info = _manifest_info(main, dependencies, resources, config, assembly_name)
    (stage / "manifest.info").write_bytes(("\r\n".join(info) + "\r\n").encode("utf-8-sig"))
    model = _manifest_model(main, dependencies, resources, config, assembly_name)
    raw = json.dumps(model, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    (stage / "manifest.ser").write_bytes(_deterministic_gzip(raw))


def _validate_manifests(stage: Path, main: Path, dependencies: Sequence[Path], resources: Sequence[Path], config: ProjectConfig, assembly_name: str) -> None:
    expected_info = ("\r\n".join(_manifest_info(main, dependencies, resources, config, assembly_name)) + "\r\n").encode("utf-8-sig")
    expected_ser = _deterministic_gzip(json.dumps(_manifest_model(main, dependencies, resources, config, assembly_name), ensure_ascii=False, separators=(",", ":")).encode("utf-8"))
    if (stage / "manifest.info").read_bytes() != expected_info:
        _fail("manifest.info identity, hashes, or line endings are invalid")
    if (stage / "manifest.ser").read_bytes() != expected_ser:
        _fail("manifest.ser identity, hashes, or deterministic gzip bytes are invalid")


def deterministic_package(stage: Path, output: Path, assembly_name: str, resource_names: Iterable[str]) -> None:
    leading = [f"{assembly_name}.config", f"{assembly_name}.dll", "manifest.info", "manifest.ser"]
    entries = list(stage.iterdir())
    if any(not entry.is_file() for entry in entries):
        _fail("CLZ staging contains a directory or non-file entry")
    names = {entry.name for entry in entries}
    if any(name not in names for name in leading):
        _fail(f"CLZ staging missing leading entry: {leading}")
    ordered = leading + sorted(names - set(leading))
    stored = {"manifest.ser", *resource_names}
    output.parent.mkdir(parents=True, exist_ok=True)
    if output.exists():
        output.unlink()
    with zipfile.ZipFile(output, "w") as archive:
        for name in ordered:
            info = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_STORED if name in stored else zipfile.ZIP_DEFLATED
            info.create_system = 0
            info.external_attr = 32
            info.flag_bits = 0
            raw = (stage / name).read_bytes()
            archive.writestr(info, raw, compress_type=info.compress_type, compresslevel=9 if info.compress_type else None)


def validate_clz(clz: Path, stage: Path, assembly_name: str, resource_names: Iterable[str]) -> None:
    stage_names = {path.name for path in stage.iterdir()}
    leading = [f"{assembly_name}.config", f"{assembly_name}.dll", "manifest.info", "manifest.ser"]
    expected = leading + sorted(stage_names - set(leading))
    stored = {"manifest.ser", *resource_names}
    try:
        with zipfile.ZipFile(clz, "r") as archive:
            infos = archive.infolist()
            if [info.filename for info in infos] != expected:
                _fail("CLZ entry order/names are not canonical")
            for info in infos:
                if info.date_time != (1980, 1, 1, 0, 0, 0) or info.create_system != 0 or info.external_attr != 32 or info.flag_bits != 0:
                    _fail(f"CLZ entry metadata is not deterministic: {info.filename}")
                expected_compression = zipfile.ZIP_STORED if info.filename in stored else zipfile.ZIP_DEFLATED
                if info.compress_type != expected_compression:
                    _fail(f"CLZ entry compression is not compatible: {info.filename}")
                if archive.read(info.filename) != (stage / info.filename).read_bytes():
                    _fail(f"CLZ entry differs from staged source: {info.filename}")
    except zipfile.BadZipFile as error:
        _fail(f"CLZ is not a readable ZIP: {error}")


def _validate_target(directory: Path, clz: Path, main: Path, config: ProjectConfig) -> None:
    expected = sorted([clz.name, main.name] + [module.filename for module in config.modules] + [module.header_filename for module in config.modules])
    actual = sorted(path.name for path in directory.iterdir())
    if actual != expected:
        _fail(f"target {directory.name} output entries mismatch: {actual}")
    if (directory / clz.name).read_bytes() != clz.read_bytes() or (directory / main.name).read_bytes() != main.read_bytes():
        _fail(f"target {directory.name} package or assembly differs from canonical output")


def _validate_sources(config: ProjectConfig, assembly_name: str) -> None:
    _assert_file(config.project_file, "MSBuild project")
    for module in config.resolved_modules:
        _assert_file(module, "SIMPL+ source")
    names = [path.name.lower() for path in config.resolved_dependencies + config.resolved_resources]
    if len(names) != len(set(names)):
        _fail("package dependencies/resources contain duplicate filenames")
    reserved = {
        f"{assembly_name}.dll".lower(),
        f"{assembly_name}.config".lower(),
        "manifest.info",
        "manifest.ser",
        "toolchain.lock.json",
        "toolchain.local.json",
        ".clz-builder.lock",
    }
    collisions = sorted(name for name in names if name in reserved)
    if collisions:
        _fail(f"package dependency/resource collides with reserved CLZ entry: {', '.join(collisions)}")


def _build_once(config: ProjectConfig, tools: Mapping[str, Path], options: BuildOptions, label: str) -> tuple[dict[str, str], Path]:
    assembly_name = config.effective_assembly_name()
    root = config.resolved_build_dir / options.configuration
    if root.exists():
        if (root / "publish-backup").exists():
            _fail(f"incomplete previous publish backup exists: {root / 'publish-backup'}")
        shutil.rmtree(root)
    root.mkdir(parents=True, exist_ok=True)
    project = config.project_file
    print(f"=== CLZ build {assembly_name} {options.configuration} {label}===", flush=True)
    _run(
        [
            tools["msbuild"], project, "/tv:3.5", "/t:Rebuild", "/p:Configuration=" + options.configuration,
            "/p:Platform=AnyCPU", "/p:FrameworkPathOverride=" + str(tools["cf"]),
            "/p:CompactFrameworkPath=" + str(tools["cf"]), "/p:CscToolPath=" + str(tools["csc"].parent),
            "/p:CscToolExe=csc.exe", "/p:CrestronProgrammingPath=" + str(tools["cresdb"]),
            "/p:CrestronReferencePath=" + str(tools["references"]), "/v:m", "/nologo",
        ],
        cwd=config.root,
    )
    output_relative = config.assembly_output.format(configuration=options.configuration, name=assembly_name, version=config.version)
    main_source = project.parent / output_relative
    _assert_file(main_source, "MSBuild output")
    main = root / "assembly" / f"{assembly_name}.dll"
    main.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(main_source, main)
    helper = _ensure_signer(tools, root)
    mvid = stable_mvid(config, config.resolved_lock_path, assembly_name)
    _run([helper, "patch", main, tools["cecil"], tools["custom_attributes"], mvid], cwd=config.root)
    _run([helper, "sign", main, tools["compiler"], tools["services"], tools["ionic"], main.parent, tools["cresdb"], OFFICIAL_SIGNER_THUMBPRINT], cwd=config.root)

    stage = root / "clz" / "staging"
    stage.mkdir(parents=True, exist_ok=True)
    shutil.copy2(main, stage / main.name)
    dependencies = [tools["custom_attributes"], tools["helper_reference"], *config.resolved_dependencies]
    resources = [tools["data_file"], tools["data_signature"], *config.resolved_resources]
    seen: set[str] = set()
    for source in [*dependencies, *resources]:
        if source.name.lower() in seen:
            _fail(f"duplicate CLZ entry filename: {source.name}")
        seen.add(source.name.lower())
        _assert_file(source, "CLZ dependency/resource")
        shutil.copy2(source, stage / source.name)
    _write_program_config(stage, config, assembly_name)
    _write_manifests(stage, stage / main.name, dependencies, resources, config, assembly_name)
    _validate_manifests(stage, stage / main.name, dependencies, resources, config, assembly_name)
    clz = root / "clz" / f"{assembly_name}.clz"
    deterministic_package(stage, clz, assembly_name, [resource.name for resource in resources if resource.name in {tools["data_file"].name, tools["data_signature"].name}])
    validate_clz(clz, stage, assembly_name, [tools["data_file"].name, tools["data_signature"].name])

    publish_root = root / "publish"
    outputs: list[Path] = []
    targets = options.targets or config.targets
    for target in targets:
        target_root = root / "modules" / target
        target_root.mkdir(parents=True, exist_ok=True)
        target_publish = publish_root / target
        target_publish.mkdir(parents=True, exist_ok=True)
        shutil.copy2(clz, target_root / clz.name)
        for module in config.modules:
            source = config.root / module.source
            staged = target_root / module.filename
            normalized = source.read_text(encoding="utf-8").replace("\r\n", "\n").replace("\r", "\n")
            try:
                staged.write_bytes(normalized.replace("\n", "\r\n").encode("ascii"))
            except UnicodeEncodeError as error:
                _fail(f"SIMPL+ source must be ASCII for SPlusCC ({source}): {error}")
            _run([tools["spluscc"], "\\rebuild", staged, "\\target", target], cwd=target_root)
            generated = target_root / module.header_filename
            _assert_file(generated, "SPlusCC header output")
            shutil.copy2(staged, target_publish / staged.name)
            shutil.copy2(generated, target_publish / generated.name)
            outputs.extend([target_publish / staged.name, target_publish / generated.name])
        shutil.copy2(clz, target_publish / clz.name)
        shutil.copy2(main, target_publish / main.name)
        _validate_target(target_publish, clz, main, config)
        outputs.extend([target_publish / clz.name, target_publish / main.name])
    if set(targets) == {"series3", "series4"}:
        for name in (clz.name, main.name):
            if (publish_root / "series3" / name).read_bytes() != (publish_root / "series4" / name).read_bytes():
                _fail(f"{name} differs between series3 and series4 staging")
    snapshot = {str(path.relative_to(config.root)).replace("\\", "/"): sha256(path) for path in outputs}
    print(f"CLZ sha256={sha256(clz)}", flush=True)
    return snapshot, publish_root


def publish_transaction(config: ProjectConfig, publish_root: Path, targets: Sequence[str], configuration: str) -> None:
    dist = config.resolved_dist_dir
    backup_root = config.resolved_build_dir / configuration / "publish-backup"
    if backup_root.exists():
        _fail(f"incomplete previous publish backup exists: {backup_root}")
    for target in targets:
        source = publish_root / target
        if not source.is_dir() or source.is_symlink():
            _fail(f"publish staging missing target: {source}")
    dist.mkdir(parents=True, exist_ok=True)
    records: list[dict[str, object]] = []
    try:
        for target in targets:
            source, destination, backup = publish_root / target, dist / target, backup_root / target
            had = destination.exists() or destination.is_symlink()
            record = {"destination": destination, "backup": backup, "had": had, "backed": False, "installed": False}
            records.append(record)
            if had:
                backup.parent.mkdir(parents=True, exist_ok=True)
                try:
                    shutil.move(str(destination), str(backup))
                except OSError:
                    # A move may report failure after creating the backup.
                    # Preserve that state for rollback instead of deleting the
                    # only remaining copy of the previous publication.
                    record["backed"] = backup.exists() or backup.is_symlink()
                    raise
                record["backed"] = True
            try:
                shutil.move(str(source), str(destination))
            except OSError:
                # Account for filesystems that report an error after creating
                # the destination directory.
                record["installed"] = destination.exists() or destination.is_symlink()
                raise
            record["installed"] = True
    except (OSError, BuildError) as error:
        rollback_errors: list[str] = []
        for record in reversed(records):
            try:
                destination = record["destination"]  # type: ignore[assignment]
                backup = record["backup"]  # type: ignore[assignment]
                if (record["installed"] or record["backed"]) and (destination.exists() or destination.is_symlink()):
                    _remove(destination)
                if record["backed"] and (backup.exists() or backup.is_symlink()):
                    shutil.move(str(backup), str(destination))
            except OSError as rollback_error:
                rollback_errors.append(str(rollback_error))
        if rollback_errors:
            _fail(f"publish failed; rollback incomplete, backup retained at {backup_root}: {' | '.join(rollback_errors)}")
        if backup_root.exists():
            _remove(backup_root)
        _fail(f"publish failed; previous dist was restored: {error}")
    if backup_root.exists():
        _remove(backup_root)


def build(config: ProjectConfig, options: BuildOptions) -> None:
    assembly_name = config.effective_assembly_name()
    _validate_sources(config, assembly_name)
    targets = options.targets or config.targets
    if not targets or any(target not in ("series3", "series4") for target in targets):
        _fail("targets must contain only series3 and/or series4")
    options = BuildOptions(options.configuration, tuple(dict.fromkeys(targets)), options.verify_reproducible, options.publish, options.recover_lock)
    try:
        tools = resolve_tools(config)
        verify_lock(config, tools)
    except ToolchainError as error:
        _fail(str(error))
    from .toolchain import build_lock
    with build_lock(config, options.recover_lock):
        first, publish_root = _build_once(config, tools, options, "pass 1 ")
        if options.verify_reproducible:
            second, publish_root = _build_once(config, tools, options, "pass 2 ")
            if first != second:
                differences = sorted(set(first) | set(second))
                detail = [f"{name}: {first.get(name)} != {second.get(name)}" for name in differences if first.get(name) != second.get(name)]
                _fail("reproducibility mismatch:\n" + "\n".join(detail))
            print("reproducible=PASS (two clean builds, byte-identical artifacts)")
        if options.publish:
            publish_transaction(config, publish_root, options.targets, options.configuration)
            for target in options.targets:
                print(f"target={target} files={len(list((config.resolved_dist_dir / target).glob('*')))}")
    print("build=PASS")
