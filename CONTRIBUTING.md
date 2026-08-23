# Contributing

Thanks for helping improve Crestron3SeriesCLZBuilder.

## Before opening a change

1. Read the README and the relevant build/security documentation.
2. Keep open-source code, docs, tests, and scripts separate from proprietary
   SDK inputs.
3. Do not commit DLL/EXE files, CLZ/USH output, certificates, private keys,
   PSKs, customer paths, or local `.clz-builder` cache files.
4. Use a focused branch and explain which configuration/toolchain assumptions
   the change relies on.

## Local checks

For documentation/scripts-only changes:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy Bypass
.\scripts\Test-Toolchain.ps1
git diff --check
```

For core changes, create a local virtual environment and run the project's
Python tests. On a licensed Windows host, run `doctor`, verify the lock, then
run the selected build and (when appropriate) `-VerifyReproducible`. A public
CI pass does not replace SPlusCC (Crestron's SIMPL+ compiler), signing, SIMPL
Windows import, or hardware acceptance.

## Pull requests

Describe the config used, commands run, and what could not be tested because a
proprietary toolchain or processor was unavailable. Keep generated output out
of screenshots and logs. Changes to signing, lock validation, path handling,
or PowerShell execution require explicit security review.

By contributing, you agree that your work is provided under the repository
license and that you have the right to submit it.
