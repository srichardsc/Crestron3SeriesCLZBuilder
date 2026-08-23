# Writing 3-Series-compatible drivers with Visual Studio 2022

Visual Studio 2022 can edit, compile, and package a legacy SIMPL# driver, but
the editor version does not change the runtime. A driver that must run on a
3-Series processor still has to target the Compact Framework and use the
interfaces supplied by the installed Crestron SDK.

This page describes the rules that matter when creating a new driver. The
builder accepts an existing `.csproj`; it does not create or redistribute the
SDK project templates.

## 1. Start from an SDK project

Create the project with the SIMPL# template or project files installed with
your licensed SDK. Point the builder at that project:

```powershell
python -m crestron_clz_builder init `
  --config .\clz-builder.json `
  --project .\Project\Driver.csproj `
  --name Driver
```

Keep the project file under source control. It should define the assembly name,
source files, configuration names, Compact Framework references, and the
SDK-provided MSBuild imports. Do not replace those imports with desktop .NET
imports just to make the project load in VS2022. If VS2022 asks for a missing
legacy target, install the supported SDK/CF reference pack and fix the project
or its local path configuration; do not copy a target file from another
machine into this repository.

The selected project should produce one library with a stable assembly name.
Use a normal `Release` configuration for packaging and keep the output path
explicit in `assembly.output` when the project does not use the default
`bin/{configuration}/{name}.dll` layout.

## 2. Compile for the Compact Framework, not desktop .NET

The 3-Series runtime constraint is the important part:

- use the Compact Framework 3.5 references supplied by the supported toolchain;
- reference only Crestron SDK assemblies intended for that target;
- keep the project platform and compiler settings from the SDK template;
- do not retarget to .NET Framework 4.x, .NET Core, .NET 6+, or .NET Standard;
- do not add NuGet packages that require a desktop CLR or APIs absent from CF.

VS2022 is the build host. It is not evidence that a desktop API will run on the
processor. Avoid assuming that `System.Net.Http`, desktop configuration APIs,
modern async/runtime helpers, filesystem watchers, or reflection-heavy
libraries are available. When an API is not present in the installed CF
references, use the supported lower-level API or keep that work on the Home
side of the integration.

Use the references already present in the SDK project and let `doctor` report
their paths. Never commit vendor DLLs to make IntelliSense or a local build
pass:

```powershell
.\.venv\Scripts\python.exe -m crestron_clz_builder doctor `
  --config .\clz-builder.json
```

## 3. Keep the driver lifecycle small and explicit

Processor code is long-lived. Make startup, reconnect, timers, worker threads,
and disposal visible in the code. A minimal shape is easier to test against a
real processor than a large static initialization graph:

```csharp
public sealed class DriverController : System.IDisposable
{
    private bool _started;
    private bool _disposed;

    public void Start()
    {
        if (_disposed || _started)
            return;

        // Create connections and timers here.
        _started = true;
    }

    public void Stop()
    {
        if (!_started)
            return;

        // Stop workers, unsubscribe events, and close sockets here.
        _started = false;
    }

    public void Dispose()
    {
        if (_disposed)
            return;

        Stop();
        _disposed = true;
    }
}
```

For a real driver, replace the comments with the SDK's supported device and
transport classes. Do not start threads or open sockets from a static field.
Do not let a reconnect callback create a second worker. Bound queues, timeouts,
and retry delays so a network failure cannot consume processor resources.

Configuration belongs in the driver configuration contract or the selected
Home-side component. Do not bake customer IP addresses, credentials, or
machine paths into the assembly.

## 4. Design the SIMPL+ boundary before writing the package

If the driver has a SIMPL+ interface, keep each `.usp` source in the selected
configuration and give its symbols stable names. Crestron's `SPlusCC` SIMPL+
compiler builds every selected module once per requested target:

```json
{
  "schema": 1,
  "assembly": {
    "project": "Project/Driver.csproj",
    "name": "Driver",
    "version": "1.0.0.0"
  },
  "modules": [
    { "source": "SIMPL/Driver.usp" }
  ],
  "targets": ["series3", "series4"]
}
```

Keep symbol names, joins, parameter order, and signal direction stable once a
driver is in use. Put target-specific behavior in the module/compiler input,
not in a second copy of the assembly. When no SIMPL+ module is needed, set
`modules` to an empty list and build a DLL/CLZ-only package.

## 5. Build and inspect a driver

Run the checks in this order:

```powershell
# Find local tools and references.
.\.venv\Scripts\python.exe -m crestron_clz_builder doctor --config .\clz-builder.json

# Record reviewed tool identities and hashes.
.\.venv\Scripts\python.exe -m crestron_clz_builder lock --config .\clz-builder.json

# Fast compile while developing the 3-Series symbol.
.\scripts\Build.ps1 -Config .\clz-builder.json -Targets series3

# Release evidence for both processor generations.
.\scripts\Build.ps1 `
  -Config .\clz-builder.json `
  -Targets series3,series4 `
  -VerifyReproducible
```

Review the output before importing it:

- MSBuild completed the selected `Release` project;
- the assembly name, version, and expected entry point match the config;
- official SDK assembly verification/signing succeeded;
- each requested target has the expected `.ush` symbols;
- package manifests and SHA-256 values validate;
- the second build produces the same bytes.

The assembly and CLZ are shared. Crestron's SPlusCC SIMPL+ compiler receives
the target separately, so the `.ush` output is target-specific. A CLZ built
through the 3-Series flow can therefore be used for a 4-Series output when the
processor model, firmware, and driver API support it. Confirm that in the
acceptance test; do not infer it from a successful local build alone.

## 6. Test on hardware

A build proves that the package is internally consistent. It does not prove
that a processor accepts the package or that the driver behaves correctly.
Record, for each tested processor:

1. model and firmware;
2. SIMPL Windows and Toolbox versions;
3. import result and any compiler/import diagnostics;
4. reboot and reconnect behavior;
5. representative inputs, outputs, errors, and recovery after a network loss;
6. final CLZ, DLL, and `.ush` SHA-256 values.

Test at least one 3-Series processor for the 3-Series symbol and one 4-Series
processor when publishing both targets. Keep hardware logs outside the public
repository if they contain customer addresses, credentials, or proprietary
diagnostics.

## Compatibility checklist

- [ ] Project comes from the supported SDK/CF template.
- [ ] Target references are Compact Framework 3.5 references.
- [ ] No desktop-only framework or NuGet dependency is required at runtime.
- [ ] Assembly identity and package metadata are stable.
- [ ] Lifecycle, reconnect, timer, and disposal paths are bounded and idempotent.
- [ ] No customer IP, hostname, secret, certificate, or machine path is in source.
- [ ] SIMPL+ symbols and joins are stable and documented.
- [ ] `doctor`, `lock`, `Build.ps1 -Targets series3`, and reproducibility checks pass.
- [ ] 3-Series hardware acceptance is recorded before release.
