"""Command line entry point for the standalone CLZ builder.

Human-facing commands render an actionable checklist; ``doctor --json`` keeps
the machine-readable contract consumed by scripts and continuous integration.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import sys

from . import __version__
from .builder import BuildError, BuildOptions, build
from .config import ConfigError, bump_version, default_config, load_config
from .toolchain import (
    ToolchainProbe,
    ToolchainError,
    probe_toolchain,
    resolve_tools,
    verify_lock,
    write_lock,
)


def _config_path(value: str) -> Path:
    return Path(value).resolve()


def _load(value: str):
    return load_config(_config_path(value))


def _parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="crestron-clz", description="Build deterministic CLZ packages with an installed Crestron toolchain")
    parser.add_argument("--version", action="version", version=f"crestron-clz {__version__}")
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

    setup = sub.add_parser("setup", help="guided first run: checks the host, prints exact fixes, prepares config and lock")
    setup.add_argument("--config", default=None, help="project configuration to create or verify (default: clz-builder.json)")
    setup.add_argument("--project", help="path to the SIMPL# .csproj; asked interactively when omitted")
    setup.add_argument("--module", action="append", default=[], dest="modules", help="optional .usp source; repeat for multiple modules")
    setup.add_argument("--name", help="assembly filename stem (defaults to project filename stem)")
    setup.add_argument("--force", action="store_true", help="regenerate the configuration even if it exists")
    setup.add_argument("--non-interactive", action="store_true", help="never prompt; select defaults or fail instead of asking")

    lock = sub.add_parser("lock", help="write or verify the toolchain lock")
    lock.add_argument("--config", default="clz-builder.json")
    lock.add_argument("--verify", action="store_true", help="verify existing lock instead of writing it")

    run = sub.add_parser("run", help="one-command build: auto-configures, bumps the version so Crestron Home accepts the update, compiles, signs and publishes")
    run.add_argument("--project", help="path to the SIMPL# .csproj; defaults to the configured project or the only .csproj found")
    run.add_argument("--module", action="append", default=[], dest="modules", help=".usp source; repeatable; only used when creating the configuration")
    run.add_argument("--name", help="assembly filename stem; only used when creating the configuration")
    run.add_argument("--config", default="clz-builder.json")
    run.add_argument("--configuration", choices=("Debug", "Release"), default="Release")
    run.add_argument("--targets", help="comma-separated target list; defaults to config targets")
    run.add_argument("--no-bump", action="store_true", help="keep the existing version instead of incrementing it")
    run.add_argument("--verify-reproducible", action="store_true")

    build_parser = sub.add_parser("build", help="compile, sign, package, validate and publish")
    build_parser.add_argument("--config", default="clz-builder.json")
    build_parser.add_argument("--configuration", choices=("Debug", "Release"), default="Release")
    build_parser.add_argument("--targets", help="comma-separated target list; defaults to config targets")
    build_parser.add_argument("--verify-reproducible", action="store_true")
    build_parser.add_argument("--no-publish", action="store_true", help="run all build gates but leave dist untouched")
    build_parser.add_argument("--recover-lock", action="store_true", help="recover a lock after confirming no build is running")
    return parser


def _relative_to(config_path: Path, raw_value: str, label: str) -> str:
    path = Path(raw_value)
    if not path.is_absolute():
        return path.as_posix()
    try:
        return path.resolve().relative_to(config_path.parent).as_posix()
    except ValueError as error:
        raise ConfigError(f"{label} must be inside the --config directory") from error


def _init(args: argparse.Namespace) -> int:
    config_path = _config_path(args.config)
    if config_path.exists() and not args.force:
        raise ConfigError(f"configuration already exists: {config_path}; use --force to replace it")
    project_text = _relative_to(config_path, args.project, "--project")
    modules = [_relative_to(config_path, module, "--module") for module in args.module]
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(default_config(project_text, modules, name=args.name), indent=2) + "\n", encoding="utf-8", newline="\n")
    print(f"initialized={config_path}")
    return 0


def _print_checklist(probes: list[ToolchainProbe]) -> int:
    ok_count = sum(1 for probe in probes if probe.ok)
    missing = [probe for probe in probes if not probe.ok]
    width = max(len(probe.label) for probe in probes)
    for probe in probes:
        mark = "[OK]" if probe.ok else "[MISSING]"
        print(f"{mark:<10} {probe.label.ljust(width)}   ({probe.component})")
        if not probe.ok:
            expected = f"expected at: {probe.expected_path}" if probe.expected_path else "no standard location found on this host"
            print(f"{'':<10} {expected}")
            print(f"{'':<10} fix: {probe.fix}")
    print("")
    summary = f"toolchain: {ok_count}/{len(probes)} inputs ready"
    print(summary + (f"; MISSING {len(missing)}" if missing else ""))
    if missing:
        public = sorted({probe.component for probe in missing if probe.kind == "public"})
        licensed = sorted({probe.component for probe in missing if probe.kind == "licensed"})
        builtin = sorted({probe.component for probe in missing if probe.kind == "builtin"})
        if public:
            print("public components installable from official sources:")
            for component in public:
                print(f"  - {component}")
        if builtin:
            print("Windows built-in components to verify or repair:")
            for component in builtin:
                print(f"  - {component}")
        if licensed:
            print("licensed components that must come through your authorized Crestron dealer channel:")
            for component in licensed:
                print(f"  - {component}")
        print("see docs/INSTALLATION.md for supported installation paths; this tool never downloads Crestron software.")
    return 2 if missing else 0


def _doctor(args: argparse.Namespace) -> int:
    config = _load(args.config)
    report: dict[str, object] = {
        "version": __version__,
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
        exit_code = 2
        if args.as_json:
            print(json.dumps(report, indent=2, sort_keys=True))
            return exit_code
        print(f"CLZ Builder {__version__} - toolchain check for {config.effective_assembly_name()}")
        print("")
        return _print_checklist(probe_toolchain(config))
    if args.as_json:
        print(json.dumps(report, indent=2, sort_keys=True))
        return 0
    print(f"CLZ Builder {__version__} - toolchain check for {config.effective_assembly_name()}")
    print("")
    exit_code = _print_checklist(probe_toolchain(config))
    lock_status = str(report.get("lockStatus", "not verified"))
    if exit_code == 0:
        print(f"lock: {lock_status}")
        if lock_status != "verified":
            print("fix: run 'crestron-clz lock --config <file>' deliberately after installing or updating the toolchain.")
        print("")
        print("next step: crestron-clz build --config <your-config>.json")
    return exit_code


def _prompt(message: str, *, default: str | None = None, required: bool = False, validator=None) -> str | None:
    """Ask one interactive question; returns None when stdin is unavailable."""
    while True:
        suffix = f" [{default}]" if default else ""
        try:
            answer = input(f"{message}{suffix}: ").strip()
        except EOFError:
            return None
        if not answer and default is not None:
            return default
        if not answer:
            if not required:
                return None
            print("  a value is required here.")
            continue
        if validator is not None:
            error = validator(answer)
            if error:
                print(f"  {error}")
                continue
        return answer


def _setup_wizard(args: argparse.Namespace) -> int:
    interactive = not args.non_interactive
    root = Path.cwd().resolve()
    config_name = args.config or "clz-builder.json"
    config_path = Path(config_name)
    if not config_path.is_absolute():
        config_path = root / config_name
    config_path = config_path.resolve()

    def csproj_validator(value: str) -> str | None:
        candidate = Path(value)
        resolved_candidate = candidate if candidate.is_absolute() else root / candidate
        if resolved_candidate.suffix.lower() != ".csproj":
            return f"expected a .csproj file: {resolved_candidate}"
        if not resolved_candidate.is_file():
            return f"file not found: {resolved_candidate}"
        try:
            resolved_candidate.resolve().relative_to(root)
        except ValueError:
            return f"path must stay inside {root}"
        return None

    print(f"CLZ Builder {__version__} - guided setup")
    print("=======================================")
    print("This wizard checks this PC against every toolchain input, prints the exact")
    print("fix for anything missing, and prepares your project configuration and lock.")
    print("It never downloads or installs Crestron software on your behalf.")
    print("")

    # Step 1: select the SIMPL# project.
    project_text = args.project
    if not project_text:
        projects = sorted(
            (
                path
                for path in root.rglob("*.csproj")
                if not {part.lower() for part in path.parts}.intersection({"bin", "obj", "build", ".venv"})
            ),
            key=lambda path: path.relative_to(root).as_posix(),
        )
        if not projects:
            if not interactive:
                raise ConfigError("no .csproj found under the current directory; pass --project explicitly")
            answer = _prompt("Path to your SIMPL# .csproj (relative to this folder)", required=True, validator=csproj_validator)
            if answer is None:
                raise ConfigError("no .csproj selected")
            project_text = _relative_to(config_path, answer, "--project")
        elif len(projects) == 1:
            project_text = projects[0].relative_to(root).as_posix()
            print(f"using project: {project_text}")
        elif interactive:
            print("Found SIMPL# projects:")
            for index, path in enumerate(projects, start=1):
                print(f"  {index}) {path.relative_to(root).as_posix()}")
            choice = _prompt("Select the project to build (number)", default="1")
            if choice is None or not choice.isdigit() or not 1 <= int(choice) <= len(projects):
                raise ConfigError("invalid project selection")
            project_text = projects[int(choice) - 1].relative_to(root).as_posix()
        else:
            project_text = projects[0].relative_to(root).as_posix()
            print(f"--non-interactive: selecting the first project found: {project_text}")
    else:
        error = csproj_validator(project_text)
        if error:
            raise ConfigError(error)

    # Step 2: create or keep the project configuration.
    created_config = False
    if not config_path.exists():
        init_args = argparse.Namespace(
            config=str(config_path), project=project_text, module=list(args.modules), name=args.name, force=False
        )
        if _init(init_args):
            return 1
        created_config = True
    elif args.force:
        init_args = argparse.Namespace(
            config=str(config_path), project=project_text, module=list(args.modules), name=args.name, force=True
        )
        if _init(init_args):
            return 1
        created_config = True
    else:
        print(f"configuration already exists: {config_path.name} (use --force to regenerate)")

    # Step 3: render the full toolchain checklist with fixes.
    config = load_config(_config_path(str(config_path)))
    print("")
    exit_code = _print_checklist(probe_toolchain(config))
    if created_config:
        print(f"created configuration: {config_path}")

    # Step 4: when everything is present, write the lock and hand off to build.
    if exit_code == 0:
        try:
            tools = resolve_tools(config)
            lock_path = write_lock(config, tools)
            verify_lock(config, tools)
            print(f"lock written and verified: {lock_path.name}")
        except ToolchainError as error:
            print(f"could not write the toolchain lock automatically: {error}")
            return 2
        print("")
        print("Everything is ready. Build now:")
        print(f"  crestron-clz build --config {config_path.name}")
        print("or with the PowerShell wrapper:")
        print(f"  .\\scripts\\Build.ps1 -Config .\\{config_path.name}")
        return 0
    print("")
    print("Install the components listed above, then re-run this command until the checklist is green.")
    print("Public items can be installed directly; licensed Crestron software comes through your dealer channel.")
    return exit_code


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


def _find_csproj(root: Path) -> list[Path]:
    return sorted(
        (
            path
            for path in root.rglob("*.csproj")
            if not {part.lower() for part in path.parts}.intersection({"bin", "obj", "build", "build-exe", "dist", "dist-exe", ".venv"})
        ),
        key=lambda path: path.relative_to(root).as_posix(),
    )


def _write_config(config_path: Path, project_text: str, modules: list[str], name: str | None) -> None:
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(
        json.dumps(default_config(project_text, modules, name=name), indent=2) + "\n",
        encoding="utf-8",
        newline="\n",
    )


def _run_command(args: argparse.Namespace) -> int:
    root = Path.cwd().resolve()
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = root / config_path
    config_path = config_path.resolve()

    # 1. Configuration: create it on first run, reuse it afterwards.
    created_config = False
    if not config_path.exists():
        project_text = args.project
        if not project_text:
            projects = _find_csproj(root)
            if len(projects) == 1:
                project_text = projects[0].relative_to(root).as_posix()
            elif not projects:
                raise ConfigError(f"no .csproj found under {root}; pass --project explicitly")
            else:
                print("Found SIMPL# projects; pass one explicitly or remove the extra ones:")
                for path in projects:
                    print(f"  - {path.relative_to(root).as_posix()}")
                raise ConfigError("multiple .csproj candidates; pass --project <path>")
        resolved_project = Path(project_text)
        if not resolved_project.is_absolute():
            resolved_project = root / resolved_project
        if not resolved_project.is_file():
            raise ConfigError(f"project input not found: {resolved_project}")
        _write_config(config_path, _relative_to(config_path, str(resolved_project), "--project"), list(args.modules), args.name)
        created_config = True
        print(f"created configuration: {config_path}")
    elif args.project or args.modules or args.name:
        print("note: --project/--module/--name are ignored because the configuration already exists.")

    config = load_config(_config_path(str(config_path)))

    # First run on a new configuration: discover the toolchain, write the
    # initial lock automatically, then continue. Later builds verify against
    # that lock like a deliberate `build` would.
    if created_config or not config.resolved_lock_path.is_file():
        from .toolchain import resolve_tools as _resolve, write_lock as _write_lock
        tools = _resolve(config)
        lock_path = _write_lock(config, tools)
        print(f"wrote toolchain lock: {lock_path}")

    # 2. Version bump so Crestron Home accepts the package as an update.
    previous_version = config.version
    if args.no_bump:
        new_version = previous_version
    else:
        new_version, previous_version = bump_version(previous_version)
        raw = json.loads(config_path.read_text(encoding="utf-8"))
        raw["assembly"]["version"] = new_version
        temporary = config_path.with_name(f"{config_path.name}.tmp-{os.getpid()}".replace("/", "-"))
        try:
            temporary.write_text(json.dumps(raw, indent=2) + "\n", encoding="utf-8", newline="\n")
            os.replace(str(temporary), str(config_path))
        except OSError as error:
            try:
                temporary.unlink()
            except OSError:
                pass
            raise ConfigError(f"cannot update version in {config_path}: {error}") from error
        config = load_config(_config_path(str(config_path)))
        print(f"version: {previous_version} -> {new_version} (Crestron Home will treat it as an update)")

    # 3. Build with the standard gates.
    targets = tuple(item.strip().lower() for item in args.targets.split(",") if item.strip()) if args.targets else ()
    build(config, BuildOptions(args.configuration, targets, args.verify_reproducible, True, False))
    return 0


def main(argv: list[str] | None = None) -> int:
    args = _parser().parse_args(argv)
    try:
        if args.command == "init":
            return _init(args)
        if args.command == "doctor":
            return _doctor(args)
        if args.command == "setup":
            return _setup_wizard(args)
        if args.command == "lock":
            return _lock(args)
        if args.command == "build":
            return _build(args)
        if args.command == "run":
            return _run_command(args)
        raise ConfigError(f"unsupported command: {args.command}")
    except (ConfigError, ToolchainError, BuildError, OSError, ValueError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
