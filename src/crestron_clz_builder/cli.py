"""Command line entry point for the standalone CLZ builder."""

from __future__ import annotations

import argparse
from dataclasses import replace
import json
from pathlib import Path
import sys

from .builder import BuildError, BuildOptions, build
from .config import ConfigError, default_config, load_config
from .toolchain import ToolchainError, resolve_tools, verify_lock, write_lock


def _config_path(value: str) -> Path:
    return Path(value).resolve()


def _load(value: str):
    return load_config(_config_path(value))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crestron-clz", description="Build deterministic CLZ packages with an installed Crestron toolchain")
    sub = parser.add_subparsers(dest="command", required=True)

    init = sub.add_parser("init", help="write a versioned project configuration")
    init.add_argument("--config", default="clz-builder.json")
    init.add_argument("--project", required=True, help="path to the SIMPL# .csproj, relative to --config")
    init.add_argument("--module", action="append", default=[], help="optional .usp source; repeat for multiple modules")
    init.add_argument("--name", help="assembly filename stem (defaults to project filename stem)")
    init.add_argument("--force", action="store_true", help="replace an existing configuration")

    doctor = sub.add_parser("doctor", help="validate project and installed toolchain inputs")
    doctor.add_argument("--config", default="clz-builder.json")
    doctor.add_argument("--json", action="store_true", dest="as_json")

    lock = sub.add_parser("lock", help="write or verify the toolchain lock")
    lock.add_argument("--config", default="clz-builder.json")
    lock.add_argument("--verify", action="store_true", help="verify existing lock instead of writing it")

    build_parser = sub.add_parser("build", help="compile, sign, package, validate and publish")
    build_parser.add_argument("--config", default="clz-builder.json")
    build_parser.add_argument("--configuration", choices=("Debug", "Release"), default="Release")
    build_parser.add_argument("--targets", help="comma-separated target list; defaults to config targets")
    build_parser.add_argument("--verify-reproducible", action="store_true")
    build_parser.add_argument("--no-publish", action="store_true", help="run all build gates but leave dist untouched")
    build_parser.add_argument("--recover-lock", action="store_true", help="recover a lock after confirming no build is running")
    return parser


def _init(args: argparse.Namespace) -> int:
    config_path = _config_path(args.config)
    if config_path.exists() and not args.force:
        raise ConfigError(f"configuration already exists: {config_path}; use --force to replace it")
    project = Path(args.project)
    if project.is_absolute():
        try:
            project_text = project.resolve().relative_to(config_path.parent).as_posix()
        except ValueError as error:
            raise ConfigError("--project must be inside the --config directory") from error
    else:
        project_text = project.as_posix()
    modules: list[str] = []
    for module in args.module:
        path = Path(module)
        if path.is_absolute():
            try:
                module = path.resolve().relative_to(config_path.parent).as_posix()
            except ValueError as error:
                raise ConfigError("--module must be inside the --config directory") from error
        modules.append(Path(module).as_posix())
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(default_config(project_text, modules, name=args.name), indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"initialized={config_path}")
    return 0


def _doctor(args: argparse.Namespace) -> int:
    config = _load(args.config)
    report: dict[str, object] = {
        "config": str(config.path),
        "project": str(config.project_file),
        "assembly": config.effective_assembly_name(),
        "modules": [str(path) for path in config.resolved_modules],
        "targets": list(config.targets),
        "toolchain": {},
        "lock": str(config.resolved_lock_path),
        "localCache": str(config.resolved_local_cache_path),
    }
    for path in [config.project_file, *config.resolved_modules, *config.resolved_dependencies, *config.resolved_resources]:
        if not path.is_file():
            raise ToolchainError(f"project input not found: {path}")
    try:
        tools = resolve_tools(config)
        report["toolchain"] = {name: str(path) for name, path in tools.items()}
        try:
            verify_lock(config, tools)
            report["lockStatus"] = "verified"
        except ToolchainError as error:
            report["lockStatus"] = f"not verified: {error}"
    except ToolchainError as error:
        report["toolchainStatus"] = f"not ready: {error}"
        if args.as_json:
            print(json.dumps(report, indent=2, sort_keys=True))
        raise
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
    else:
        print(f"config={config.path}")
        print(f"project={config.project_file}")
        print(f"assembly={config.effective_assembly_name()}")
        print(f"targets={','.join(config.targets)}")
        print(f"modules={len(config.modules)}")
        print(f"toolchain=READY ({len(report['toolchain'])} inputs)")
        print(f"lock={report.get('lockStatus', 'not verified')}")
    return 0


def _lock(args: argparse.Namespace) -> int:
    config = _load(args.config)
    tools = resolve_tools(config)
    if args.verify:
        verify_lock(config, tools)
        print(f"lock=VERIFIED path={config.resolved_lock_path}")
    else:
        path = write_lock(config, tools)
        print(f"lock=WRITTEN path={path}")
    return 0


def _build(args: argparse.Namespace) -> int:
    config = _load(args.config)
    targets = tuple(item.strip().lower() for item in args.targets.split(",") if item.strip()) if args.targets else ()
    build(config, BuildOptions(args.configuration, targets, args.verify_reproducible, not args.no_publish, args.recover_lock))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            return _init(args)
        if args.command == "doctor":
            return _doctor(args)
        if args.command == "lock":
            return _lock(args)
        if args.command == "build":
            return _build(args)
        raise ConfigError(f"unsupported command: {args.command}")
    except (ConfigError, ToolchainError, BuildError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
