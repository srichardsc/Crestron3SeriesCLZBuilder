"""Opt-in installed-SDK integration gate.

Set ``CRESTRON_CLZ_INTEGRATION_CONFIG`` to a real project configuration on a
Windows host with VS2022 and the Crestron SDK installed. The default unit test
run never requires proprietary inputs.
"""

from __future__ import annotations

import os
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from crestron_clz_builder.cli import main


@unittest.skipUnless(os.environ.get("CRESTRON_CLZ_INTEGRATION_CONFIG"), "set CRESTRON_CLZ_INTEGRATION_CONFIG for an installed-SDK build")
class InstalledSdkBuildTests(unittest.TestCase):
    def test_configured_project_builds_reproducibly(self) -> None:
        config = os.environ["CRESTRON_CLZ_INTEGRATION_CONFIG"]
        self.assertEqual(main(["build", "--config", config, "--verify-reproducible"]), 0)
