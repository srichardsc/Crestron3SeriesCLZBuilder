# Configuration reference

Every command selects a project with `--config <path>`. The directory that
contains that JSON file is the project root for relative configuration paths.
Use one configuration per independently built assembly; selecting a different
file selects a different project without copying or changing the builder.

## Schema 1

```json
{
  "schema": 1,
  "assembly": {
    "project": "Project/Driver.csproj",
    "name": "Driver",
    "output": "bin/{configuration}/{name}.dll",
    "version": "1.0.0.0",
    "minimumFirmware": "1.007.0017"
  },
  "modules": [
    { "source": "SIMPL/Bridge.usp" }
  ],
  "targets": ["series3", "series4"],
  "package": {
    "dependencies": [],
    "resources": [],
    "metadata": {
      "friendlyName": "Driver",
      "systemName": "Driver",
      "entryPoint": "Driver"
    }
  },
  "toolchain": { "paths": {} },
  "output": { "build": "build", "dist": "dist" }
}
```

### Top-level fields

| Field | Required | Contract |
| --- | --- | --- |
| `schema` | yes | Integer `1`. Unknown schemas fail closed. |
| `assembly` | yes | SIMPL# project, assembly identity, expected output, version, and minimum firmware. |
| `modules` | no | Zero or more `.usp` sources. Strings and `{ "source": "..." }` objects are accepted. |
| `targets` | no | Non-empty unique list containing `series3`, `series4`, or both. Default: both. |
| `package` | no | Additional package dependencies/resources and CLZ metadata. |
| `toolchain` | no | Explicit local path overrides under `paths`. Local cache and lock locations are fixed. |
| `output` | no | Dedicated staging and publication directories. |

### `assembly`

- `project` is required and resolves from the configuration directory.
- `name` is optional when the project XML contains `AssemblyName`. It must be a
  valid, non-reserved Windows filename stem.
- `output` defaults to `bin/{configuration}/{name}.dll` and resolves from the
  directory containing the selected `.csproj`. Plain `{configuration}`,
  `{name}`, and `{version}` placeholders are supported; the value must end in
  `{name}.dll`. Set it explicitly when the project changes `OutputPath`.
- `version` defaults to `1.0.0.0` and is written to the package manifest.
- `minimumFirmware` defaults to `1.007.0017`.

### Modules and package files

Module, dependency, and resource paths resolve from the configuration
directory and cannot be absolute or escape with `..`. Modules are optional;
an empty list builds a DLL/CLZ-only package. When modules exist, `SPlusCC`,
Crestron's SIMPL+ compiler, compiles each source separately for every selected
target.

Dependency/resource filenames must be unique and cannot collide with the
assembly DLL/config or `manifest.info`/`manifest.ser`. Standard Crestron helper,
custom-attribute, and data files come from the discovered SDK and do not belong
in this list or in source control.

Supported metadata keys are `friendlyName`, `systemName`, `entryPoint`,
`programTool`, `designToolId`, `programToolId`, `archiveName`,
`programmerName`, `compiledOn`, `compilerRev`, and `pluginVersion`. Values are
strings and are XML-escaped before packaging. Keep `compiledOn` stable when
byte-for-byte reproducibility matters.

### Toolchain discovery and overrides

Resolution order is explicit `toolchain.paths`, valid local cache, then host
discovery. Values may be absolute, relative to the configuration directory, or
contain Windows `%VARIABLE%` references. Supported keys are:

```text
msbuild, csc, helperCsc, spluscc, compiler, services, ionic, cecil,
cresdb, references, data, cf, cf_mscorlib, cf_system, cf_system_core,
cf_csc_rsp, cf_common_targets, cf_csharp_targets, msbuild_rsp,
helper_system, helper_reference, custom_attributes, data_file, data_signature
```

Keep machine-specific overrides local. `doctor`, `lock`, and `build` persist
resolved absolute paths only in ignored `.clz-builder/toolchain.local.json`.
The versioned `toolchain.lock.json` contains byte identity, sizes, runtime
identity, and signer identity—not absolute host paths. Schema 1 intentionally
does not allow either local-state path to be redirected.

### Output safety

`output.build` and `output.dist` resolve from the configuration directory.
Both must name dedicated relative directories; neither may be `.` or contain
the other. Builds stage and validate every selected target before
transactionally replacing `dist/<target>`.

## Commands

```powershell
# Create a new configuration.
.\.venv\Scripts\python.exe -m crestron_clz_builder init `
  --config .\clz-builder.json `
  --project .\Project\Driver.csproj `
  --module .\SIMPL\Bridge.usp `
  --name Driver

# Select that project for every later operation.
.\.venv\Scripts\python.exe -m crestron_clz_builder doctor --config .\clz-builder.json
.\.venv\Scripts\python.exe -m crestron_clz_builder lock --config .\clz-builder.json
.\scripts\Build.ps1 -Config .\clz-builder.json -VerifyReproducible
```

Review generated configuration before running `lock`. Do not store private
keys, PSKs, credentials, customer hostnames, or proprietary binaries in it.
