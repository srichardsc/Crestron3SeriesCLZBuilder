# AGENTS.md

> Guía de uso del agente para este repositorio.

## USE THIS REPO ONLY FOR:

- **"Crestron3SeriesCLZBuilder"** — herramienta open-source (Python) para construir paquetes **CLZ** de Crestron: de una carpeta de driver a un `CLZ` firmado que corre en 3-Series y 4-Series y que Crestron Home acepta como udpate.
- **CLI principal** en `src/` (empaquetado/versionado/firma), `pyproject.toml`, tests (`tests/`), scripts (`scripts/`) y ejemplos (`examples/`).
- **Empaquetado del binario** `clz-builder.exe` (`build-exe/`, spec de PyInstaller) y releases en `dist-exe/`.
- **Docs de uso, build, CI y configuración** (`docs/`: FOR-DUMMIES, BUILD, CI, CONFIGURATION, etc.) y changelog.

> Este repo NO contiene drivers C# de Crestron Home (ver `InfinityBridgeDriver`/`crestron-home-drivers`), ni el servidor MCP (ver `crestron-home-mcp`).