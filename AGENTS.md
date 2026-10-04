# AGENTS.md

> Guía de uso del agente para este repositorio.

## USE THIS REPO ONLY FOR:

- **"Crestron3SeriesCLZBuilder"** — herramienta open-source (Python) para construir paquetes **CLZ** de Crestron: de una carpeta de driver a un `CLZ` firmado que corre en 3-Series y 4-Series y que Crestron Home acepta como udpate.
- **CLI principal** en `src/` (empaquetado/versionado/firma), `pyproject.toml`, tests (`tests/`), scripts (`scripts/`) y ejemplos (`examples/`).
- **Empaquetado del binario** `clz-builder.exe` (`build-exe/`, spec de PyInstaller) y releases en `dist-exe/`.
- **Docs de uso, build, CI y configuración** (`docs/`: FOR-DUMMIES, BUILD, CI, CONFIGURATION, etc.) y changelog.

> Los productos InfinityBridge viven en `../infinitybridge/crestron/` (Home Driver, SIMPLAccess y SIMPLink); consulta su [arquitectura](../infinitybridge/crestron/docs/architecture.md) al ajustar la integración del builder. Los drivers accesorios siguen en `../crestron-home-drivers/` y el MCP en `../crestron-home-mcp/`.
