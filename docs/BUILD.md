# Build and packaging

New to the tool? Start with the [first-time guide](FOR-DUMMIES.md); this page
is the precise reference. The guided `setup` subcommand performs the first
two sections below (configuration plus doctor) and writes the lock when the
host is complete.

The command-line interface accepts a project configuration with `--config`.
That file selects the source project (`csproj`), assembly identity, optional
`.usp` modules, targets, output directory, toolchain paths, and package
metadata. The same builder can then be used for another project by selecting a
different configuration. The driver source and SDK project stay in their own
repository; this tool only compiles and packages them.

Before creating a project, read
[`DRIVER-DEVELOPMENT.md`](DRIVER-DEVELOPMENT.md). It covers the Compact
Framework constraints that still apply when VS2022 is the editor and MSBuild
host.

## Create a configuration

Use `init` to record a project and its modules. Paths must be inside the
configuration directory:

```powershell
.venv\Scripts\python.exe -m crestron_clz_builder init `
  --config .\clz-builder.json `
  --project .\Project\Driver.csproj `
  --module .\SIMPL\Bridge.usp `
  --name Driver
```

Review the generated JSON. It is the source of truth for project, assembly,
modules, targets, output, dependencies, resources, and toolchain paths.
See the exact schema and path semantics in
[`CONFIGURATION.md`](CONFIGURATION.md).

## Canonical invocation

PowerShell wrapper:

```powershell
.\scripts\Build.ps1 -Config .\clz-builder.json
```

The wrapper calls the local `.venv` package as:

```text
python -m crestron_clz_builder build --config <path> --configuration Release
```

If `.venv` is absent, it can use an installed `crestron-clz` entry point or a
Python interpreter on PATH. `Setup.ps1` creates `.venv` and installs the local
package with `pip install --editable`.

Supported per-run build controls are deliberately narrow and map to the real
CLI: `-Configuration`, `-Targets`, `-VerifyReproducible`, `-NoPublish`, and
`-RecoverLock`. Project, assembly, module, and output selection belong in
`--config`; the wrapper does not add runtime selectors outside that contract.

Equivalent direct commands:

```text
python -m crestron_clz_builder doctor --config clz-builder.json
python -m crestron_clz_builder lock --config clz-builder.json
python -m crestron_clz_builder build --config clz-builder.json --targets series3,series4
python -m crestron_clz_builder build --config clz-builder.json --verify-reproducible
```

Use `python -m crestron_clz_builder --help` and the subcommand help as the
authoritative option list for the checked-out core version.

## Configuration contract

The core owns the precise schema. A portable configuration represents at least
the following concepts (field nesting may evolve with the schema version):

```json
{
  "schema": 1,
  "assembly": {
    "project": "Project/Driver.csproj",
    "name": "Driver",
    "version": "1.0.0.0",
    "minimumFirmware": "1.007.0017"
  },
  "modules": ["SIMPL/Bridge.usp"],
  "targets": ["series3", "series4"],
  "package": { "dependencies": [], "resources": [], "metadata": {} },
  "toolchain": { "paths": {} },
  "output": { "build": "build", "dist": "dist" }
}
```

Relative paths resolve from the directory containing the configuration file.
The schema fixes the versioned lock at `toolchain.lock.json` and the ignored
host-path cache at `.clz-builder/toolchain.local.json`; project configuration
cannot redirect either file onto source or output. Do not place credentials,
private keys, signer material, customer
hostnames, or unreviewed machine-specific SDK paths in the file. Keep separate
configurations for separate products or release channels.

## Pipeline stages

The pipeline is deterministic and stops on the first invalid input. Each
console run prints its position as ``[n/total] stage: ...`` lines so a failed
stage is easy to locate and report:

1. Resolve and validate the selected config, project, assembly identity, `.usp`
   inventory, target names, output path, and required local toolchain.
2. Hash and compare toolchain inputs against `toolchain.lock.json`.
3. Run MSBuild for the selected `csproj` and configuration.
4. Produce the assembly in isolated staging, then apply the official vendor
   verification/signing service available in the installed SDK.
5. Build one deterministic `CLZ`, manifest, and dependency set from that
   verified assembly.
6. Validate package structure, manifest identity, hashes, compression, and
   timestamps before publication.
7. Run `SPlusCC.exe`, Crestron's SIMPL+ compiler, independently for each
   requested target and validate the expected `.ush` inventory and symbol
   identity.
8. Publish all requested targets transactionally. Preserve a valid prior
   output or a recovery backup if publication/rollback cannot complete.

The assembly and `CLZ` are shared between 3-Series and 4-Series outputs. Only
the target-specific `.ush` symbols are compiled separately. This is why a
3-Series CLZ can also work on 4-Series, subject to product and firmware
acceptance gates.

## Signing boundary

The build must call the official SDK service and validate its expected signer
identity. Do not substitute a self-generated certificate, a homemade signer,
or a different signing API. A locally successful ZIP/CLZ is not an acceptable
signed package unless the installed official service verifies it.

No signing key is expected in source control or in a project configuration.
If the SDK cannot verify the assembly, stop and use the supported SDK release;
do not weaken the gate.

## Outputs and evidence

The output directory is selected by configuration. A successful build should
make it possible to identify:

- selected config and source revision;
- assembly and `CLZ` SHA-256 values;
- target-specific `.ush` files and their target;
- toolchain lock status and runtime identity;
- every external command exit code.

Keep generated output out of commits unless a separate license review allows
the artifact. Hardware acceptance requires a record of model, firmware,
SIMPL Windows/Toolbox version, import result, ERRlog, reboot, reconnect, and
representative I/O behavior.
