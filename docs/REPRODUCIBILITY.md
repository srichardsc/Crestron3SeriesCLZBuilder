# Reproducibility

Reproducibility means that two clean builds from the same source, selected
configuration, and locked toolchain produce byte-identical release artifacts.
It does not mean that proprietary tools become open source or that every
machine can build without a licensed installation.

## What is locked

The toolchain lock should record hashes and sizes for all bytes that affect
the result, including:

- Python implementation/version and the runtime modules used by the packager;
- MSBuild and the Compact Framework compiler/reference assemblies;
- SPlusCC, Crestron's SIMPL+ compiler, and SIMPL# compiler/service libraries;
- Cresdb references and project data;
- response files and implicit framework targets;
- the official signer identity expected by the core.

Executable paths are diagnostic only. A path change with identical locked
bytes must not change the identity fingerprint.

Discovery details for one host are cached separately in
`.clz-builder/toolchain.local.json`. That fixed file is generated locally, contains absolute
paths, is revalidated by `doctor`, and is ignored by Git. It is convenience
state, not a reproducibility input and must never be copied to another host.
The committed `toolchain.lock.json` contains file names, hashes, sizes,
runtime identity, and signer identity—not developer PC paths.

## Verification

Run two clean staged builds and compare artifacts:

```powershell
.\scripts\Build.ps1 -Config .\clz-builder.json -VerifyReproducible
```

The pipeline must validate both builds before changing the selected output
directory. If bytes differ, keep the previous output, inspect the first
changed artifact and review runtime/toolchain lock differences.

## Deliberate lock updates

Only regenerate a lock after an intentional SDK, framework, Python, or
MSBuild change has been reviewed:

```powershell
.\.venv\Scripts\python.exe -m crestron_clz_builder lock --config .\clz-builder.json
```

Record why the input changed, the installed product versions, and the old/new
hashes in the change description. Never edit a hash by hand to silence a
failure. Never commit proprietary input files to make a lock pass.

## Sources of non-determinism

Common causes include local timestamps, absolute source paths, ZIP metadata,
compiler response files, runtime/zlib versions, generated MVIDs, unordered
module discovery, and different SDK service versions. The core should normalize
these values or include their byte identity in the lock. A reproducibility
failure is evidence to investigate, not a reason to disable the gate.

The MD5 values inside `manifest.info` and `manifest.ser` are required legacy
CLZ metadata, not a modern integrity or security primitive. Use the published
SHA-256 artifact digest and the locked toolchain for integrity evidence.
