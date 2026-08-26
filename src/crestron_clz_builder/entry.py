"""PyInstaller entry point (absolute imports only)."""

import sys
from pathlib import Path

# When frozen, package data (Signer.cs) is extracted next to the executable
# bundle root; expose it to the builder's signer lookup.
if getattr(sys, "frozen", False):
    bundle = Path(getattr(sys, "_MEIPASS", Path(sys.executable).parent))
    candidate = bundle / "crestron_clz_builder"
    if not candidate.is_dir():
        candidate = bundle
    sys.path.insert(0, str(bundle))

from crestron_clz_builder.cli import main

raise SystemExit(main())
