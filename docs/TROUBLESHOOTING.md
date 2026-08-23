# Troubleshooting

Start with a fresh `Test-Toolchain.ps1 -Json` report and the first failing
command. Do not paste proprietary binaries, credentials, signer material, or
customer network data into an issue.

## `Python 3 not found`

Install Python 3.10+ from the official distribution or run
`Setup.ps1 -InstallOpenSource`, then open a new shell so `py.exe` is on PATH.
Use the local `.venv` created by `Setup.ps1`; for a non-standard Python
installation, create that environment explicitly and rerun setup.

## `MSBuild` or CF reference missing

Install VS2022/MSBuild and the supported .NET Compact Framework 3.5
references. `EnableNetFx3` enables the public Windows feature only; it does
not install Compact Framework references. Put an approved path in the local
`toolchain.paths` config if VS2022 is installed in a non-standard edition/path.

## `SPlusCC.exe` (Crestron's SIMPL+ compiler), SIMPL# SDK, or Cresdb missing

Obtain the matching software through an authorized Crestron dealer account and
install the licensed SIMPL Windows/SPlusCC, SIMPL# SDK/SIMPLSharpService, and
Cresdb release. Re-run the checker. Do not download DLLs from a random web
site or copy them into this repository. Use local
`toolchain.paths` entries for a supported side-by-side installation.

## Configuration or selector errors

Confirm that `-Config` exists, is valid JSON, and points to the intended
`csproj`, assembly, `.usp` inventory, target list, and output directory.
Relative paths resolve from the configuration root. Use `-Targets` to test a
one-off target selection without editing the shared config. Project and module
selection belongs in the config created by `init`.

## Toolchain lock mismatch

The mismatch means an input changed or a different runtime is being used.
Compare the report with the lock and verify the installed product version.
Only after an intentional review run `python -m crestron_clz_builder lock
--config .\clz-builder.json`; never hand-edit hashes or copy proprietary files
into source control.

## Local discovery cache is stale

Delete or regenerate `.clz-builder/toolchain.local.json` only after confirming
no build is running, then run:

```powershell
.\.venv\Scripts\python.exe -m crestron_clz_builder doctor --config .\clz-builder.json
```

The cache contains absolute paths for one PC. It is not the committed lock,
must remain ignored, and must not be copied to another workstation.

## Assembly verification/signing failure

Stop. Check that the SIMPL# SDK and SIMPLSharpService versions match the
project's supported toolchain and that the official signer service is present.
Do not replace it with a self-generated certificate, a homemade signer, or a
different signing API.

## SPlusCC (SIMPL+) or CLZ import failure

Check the external process exit code, target name, generated `.ush` inventory,
assembly identity, manifest hashes, and CLZ entry structure. Rebuild in clean
staging and compare SHA-256 values. A successful local package still requires
SIMPL Windows/Toolbox import and hardware acceptance.

## Stale build lock

Confirm that no build is running. Then use the core's explicit recovery option:

```powershell
.\.venv\Scripts\python.exe -m crestron_clz_builder lock --config .\clz-builder.json
.\scripts\Build.ps1 -Config .\clz-builder.json -RecoverLock
```

If recovery fails, preserve the lock and report its metadata; do not delete a
live lock while another build may be running.
