from __future__ import annotations

from pathlib import Path
import sys
import tempfile
import unittest
import zipfile

sys.path.insert(0, str(Path(__file__).parents[1] / "src"))

from crestron_clz_builder.builder import BuildError, deterministic_package, validate_clz


class PackageTests(unittest.TestCase):
    def make_stage(self, root: Path) -> Path:
        stage = root / "stage"
        stage.mkdir()
        for name, content in {
            "Example.config": b"config\r\n",
            "Example.dll": b"assembly",
            "manifest.info": b"info\r\n",
            "manifest.ser": b"serialized",
            "SimplSharpCustomAttributesInterface.dll": b"custom",
            "SimplSharpHelperInterface.dll": b"helper",
            "SimplSharpData.dat": b"data",
            "SimplSharpData.dat.der": b"signature",
        }.items():
            (stage / name).write_bytes(content)
        return stage

    def test_package_is_byte_stable_and_validated(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = self.make_stage(root)
            first = root / "first.clz"
            second = root / "second.clz"
            deterministic_package(stage, first, "Example", ("SimplSharpData.dat", "SimplSharpData.dat.der"))
            deterministic_package(stage, second, "Example", ("SimplSharpData.dat", "SimplSharpData.dat.der"))
            self.assertEqual(first.read_bytes(), second.read_bytes())
            validate_clz(first, stage, "Example", ("SimplSharpData.dat", "SimplSharpData.dat.der"))
            with zipfile.ZipFile(first) as archive:
                self.assertEqual(archive.namelist()[:4], ["Example.config", "Example.dll", "manifest.info", "manifest.ser"])
                self.assertEqual(archive.getinfo("SimplSharpData.dat").compress_type, zipfile.ZIP_STORED)
                self.assertEqual(archive.getinfo("Example.dll").compress_type, zipfile.ZIP_DEFLATED)

    def test_validation_rejects_tampered_package_entry(self) -> None:
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            stage = self.make_stage(root)
            package = root / "package.clz"
            deterministic_package(stage, package, "Example", ("SimplSharpData.dat", "SimplSharpData.dat.der"))
            (stage / "Example.dll").write_bytes(b"changed-after-package")
            with self.assertRaises(BuildError):
                validate_clz(package, stage, "Example", ("SimplSharpData.dat", "SimplSharpData.dat.der"))
