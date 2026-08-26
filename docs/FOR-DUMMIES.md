# CLZ Builder for absolute beginners

## TL;DR — the whole workflow in two lines

One time, on the build PC:

```powershell
git clone https://github.com/srichardsc/Crestron3SeriesCLZBuilder.git; Set-Location Crestron3SeriesCLZBuilder; .\scripts\Setup.ps1
```

Every build, forever (from your driver's folder):

```powershell
C:\path\to\Crestron3SeriesCLZBuilder\.venv\Scripts\python.exe -m crestron_clz_builder run
```

That is it. First `run` configures everything; every later `run` bumps the
version so Crestron Home accepts the update, builds and signs the CLZ into
`dist\series3` and `dist\series4`. The rest of this guide explains each step.

---

This guide assumes you have **never** used the tool, have never heard of a
Python virtual environment, and just want your SIMPL# driver turned into a
`.clz` file that SIMPL Windows can load. Follow the steps in order. Do not skip
step 1.

> One thing no tool can do for you: this builder drives compilers that
> **you** must have installed and licensed (SIMPL Windows, SIMPL# SDK,
> Cresdb, .NET Compact Framework 3.5). The tool checks what is missing and
> tells you exactly what to install — but it never downloads or installs
> Crestron software on your behalf.

---

## The big picture in 30 seconds

```text
Your SIMPL# project (.csproj)  +  optional SIMPL+ modules (.usp)
        │
        ▼  clz-builder setup     ← checks your PC, prints exact fixes
        ▼  clz-builder build     ← compiles, signs, packages, validates
        ▼
dist\series3\  dist\series4\    ← Driver.clz + .usp + .ush ready to import
        │
        ▼
SIMPL Windows → import the .clz → compile program → download to processor
```

You will type commands. Copy them exactly. The two you will actually use every
day are `setup` and `build`.

---

## Step 0 — Know what you need before you start

| You need | Why | Where it comes from |
| --- | --- | --- |
| Windows 10/11 x64 | all build tools are Windows-only | your PC |
| This repository | the builder itself | `git clone` (below) |
| Python 3.10+ | runs the builder | public; installer offered by Setup.ps1 |
| Visual Studio 2022 + MSBuild | compiles C# | public Microsoft download |
| .NET Framework 3.5 (Windows feature) | legacy compiler bits | Windows features / Setup.ps1 |
| .NET Compact Framework 3.5 | SIMPL# targets it | via Crestron-supported installation |
| SIMPL Windows (with SPlusCC.exe) | compiles SIMPL+ to `.ush` | licensed Crestron dealer channel |
| SIMPL# SDK + SIMPLSharpService | signs your assembly | licensed Crestron dealer channel |
| Cresdb Programming data | SDK references + data files | licensed Crestron dealer channel |

Not sure what you already have? That is exactly what Step 2 finds out.

## Step 1 — Install the builder (one time)

Open PowerShell in the folder where you keep code:

```powershell
git clone https://github.com/srichardsc/Crestron3SeriesCLZBuilder.git
Set-Location .\Crestron3SeriesCLZBuilder
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass   # only affects this window
.\scripts\Setup.ps1
```

`Setup.ps1` creates an isolated Python environment inside the repo folder and
installs the tool into it. It touches nothing else on your system.

Optional helpers, only if you need them:

```powershell
.\scripts\Setup.ps1 -InstallOpenSource    # installs Python 3.12 via winget
.\scripts\Setup.ps1 -InstallBuildTools    # installs VS2022 Build Tools (MSBuild) via winget
.\scripts\Setup.ps1 -EnableNetFx3         # enables the Windows .NET Framework 3.5 feature (admin)
```

**Prefer zero Python?** After running Setup once on any machine, build a
portable executable and copy it wherever you like:

```powershell
.\scripts\MakeExecutable.ps1
# produces dist-exe\clz-builder.exe — a single file, no Python needed to run it
```

## Step 2 — Let the wizard check your PC

From the repository folder:

```powershell
.\.venv\Scripts\python.exe -m crestron_clz_builder setup
```

(With the portable executable: `clz-builder.exe setup`.)

The wizard:

1. Finds your SIMPL# project (asks if there are several).
2. Creates your configuration file `clz-builder.json`.
3. Prints a checklist of **all 24 toolchain inputs**, green or missing.
4. For each missing item: shows where it looked, why it matters, and the fix.
5. If everything is present, writes the reproducibility lock and prints the
   exact build command.

Example of what a missing item looks like:

```text
[MISSING]  SPlusCC.exe (Crestron's SIMPL+ compiler)   (SIMPL Windows)
           expected at: C:\Program Files (x86)\Crestron\Simpl\SPlusCC.exe
           fix: install SIMPL Windows through your authorized Crestron dealer (docs/INSTALLATION.md)

toolchain: 21/24 inputs ready; MISSING 3
licensed components that must come through your authorized Crestron dealer channel:
  - SIMPL Windows
```

Install whatever it lists, run `setup` again, repeat until it is green. Items
marked *public* can be fixed with the `Setup.ps1` helpers above; items marked
*licensed* come through your dealer channel — the tool will never download them.

## Step 3 — Build

The wizard printed the exact command at the end. It looks like this:

```powershell
.\.venv\Scripts\python.exe -m crestron_clz_builder build --config clz-builder.json
# or simply, with the wrapper:
.\scripts\Build.ps1 -Config clz-builder.json
# or with the portable executable:
clz-builder.exe build --config clz-builder.json
```

While it runs you will see numbered stages, so you always know where you are:

```text
=== CLZ build MyDriver Release pass 1 ===
[1/6] stage: MSBuild compile (Release, Compact Framework 3.5)
...MSBuild output...
[2/6] stage: prepare official signer helper
[3/6] stage: patch MVID and sign with the official SIMPL# service
[4/6] stage: package deterministic CLZ with manifests
[5/6] stage: SPlusCC compile Bridge.usp for series3
[6/6] stage: publish series3

=== build summary ===
  assembly : MyDriver.dll (9f3c…)
  package  : MyDriver.clz (7be2…)
  target   : series4 - 4 files in dist: …\dist\series4
  time     : 38.2s pass 1

Next steps:
  1. Import MyDriver.clz from SIMPL Windows (File > Export/Import > Load Program Package).
  ...
build=PASS
```

If a stage fails, the error appears right under its `[n/6] stage:` line — that
line is also what you paste when asking for help.

Add `-VerifyReproducible` (or `--verify-reproducible`) to make the tool build
everything twice from scratch and prove both artifacts are byte-identical.
Recommended before releasing to production.

## Step 4 — Use what was built

Inside `dist\series3\` and `dist\series4\` you get:

| File | What it is | What you do with it |
| --- | --- | --- |
| `MyDriver.clz` | the signed package | import into SIMPL Windows |
| `MyDriver.dll` | the compiled assembly | informational copy |
| `Bridge.usp` | your SIMPL+ module source | drop into your SIMPL program as needed |
| `Bridge.ush` | compiled SIMPL+ header per target | required by SIMPL+ modules in your program |

In SIMPL Windows: *File → Export/Import → Load Program Package…*, pick the
`.clz`, then add the symbol to your program, compile, and download to the
processor. Reboot the processor once and check `ERRlog`.

A clean local build is **not** hardware acceptance — test on real hardware.

## Everyday cheat sheet

```powershell
# check the PC again after installing something
python -m crestron_clz_builder doctor --config clz-builder.json

# normal build
.\scripts\Build.ps1 -Config clz-builder.json

# release-grade build (proves byte-identical output)
.\scripts\Build.ps1 -Config clz-builder.json -VerifyReproducible

# try one target only, without touching dist
python -m crestron_clz_builder build --config clz-builder.json --targets series4 --no-publish
```

## When something goes wrong

| Symptom | Meaning | Fix |
| --- | --- | --- |
| `setup` lists missing items | those components are not installed (or paths moved) | follow each printed `fix:` line |
| `toolchain lock missing` | first build on this host | run the command printed next to the message (the `lock` subcommand), or rerun `setup` |
| `toolchain input changed (...)` | an SDK/tool binary changed after the lock was written | intentional update? run the `lock` subcommand deliberately; otherwise investigate |
| `command failed (...): MSBuild` | your C# does not compile | read the MSBuild errors above the message |
| `SIMPL+ source must be ASCII for SPlusCC` | non-ASCII characters in a `.usp` | remove accents/smart quotes from the `.usp` |
| `incomplete previous publish backup exists` | a previous run died mid-publish | verify nothing is writing there, delete the folder named `publish-backup` |
| `error: configuration not found` | wrong folder or wrong `--config` path | run from the folder that contains `clz-builder.json`, or pass the full path |

Deeper problems: see [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md).

## Vocabulary for humans

- **CLZ** — a signed zip-like package SIMPL Windows imports; contains your DLL plus metadata.
- **SPlusCC** — Crestron's SIMPL+ compiler; turns `.usp` into `.ush`.
- **Toolchain** — the set of installed programs/files needed to build (MSBuild, SPlusCC, SDK DLLs…).
- **Lock (`toolchain.lock.json`)** — fingerprints of the exact toolchain binaries used, so anyone can reproduce your artifact.
- **dist** — final output folder you actually use. Everything under `build\` is scratch space.
