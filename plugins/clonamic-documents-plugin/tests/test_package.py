import json
import importlib.util
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def load_script(name):
    path = ROOT / "skills" / "clonamic-hwpx" / "scripts" / name
    spec = importlib.util.spec_from_file_location(f"clonamic_hwpx_{path.stem}", path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


class PackageTest(unittest.TestCase):
    def test_manifest_and_skill_are_closed(self):
        manifest = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
        self.assertEqual("clonamic-documents-plugin", manifest["name"])
        self.assertEqual(["clonamic-hwpx"], [p.parent.name for p in (ROOT / "skills").glob("*/SKILL.md")])

    def test_text_and_table_extraction_use_only_the_standard_library(self):
        text = load_script("extract_text.py")
        tables = load_script("extract_tables.py")
        section = b'''<?xml version="1.0" encoding="UTF-8"?>
        <hp:section xmlns:hp="http://www.hancom.co.kr/hwpml/2011/paragraph">
          <hp:p><hp:run><hp:t>Hello</hp:t></hp:run></hp:p>
          <hp:tbl><hp:tr><hp:tc><hp:p><hp:run><hp:t>Cell</hp:t></hp:run></hp:p></hp:tc></hp:tr></hp:tbl>
        </hp:section>'''
        self.assertEqual(["Hello", "Cell"], text.extract_text_from_section(section))
        self.assertEqual([[["Cell"]]], tables.extract_tables_from_section(section))

    def test_office_helper_never_builds_or_loads_a_temp_shared_library(self):
        source = (
            ROOT / "skills/clonamic-hwpx/scripts/office/soffice.py"
        ).read_text(encoding="utf-8")
        for forbidden in ("LD_PRELOAD", "lo_socket_shim", "gcc", "_SHIM_SOURCE"):
            self.assertNotIn(forbidden, source)

    def test_manifest_validation_fails_closed_without_third_party_parsers(self):
        validate = load_script("validate.py")
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            contents = root / "Contents"
            contents.mkdir()
            (contents / "content.hpf").write_text(
                '<package xmlns="http://www.idpf.org/2007/opf">'
                '<manifest><item id="image1" href="BinData/missing.png"/></manifest>'
                '</package>',
                encoding="utf-8",
            )
            validator = validate.HWPXValidator(str(root))
            validator.work_dir = root
            validator._check_manifest_consistency()
            self.assertTrue(
                any(result.check == "MANIFEST" for result in validator.report.errors)
            )
        source = (
            ROOT / "skills/clonamic-hwpx/scripts/validate.py"
        ).read_text(encoding="utf-8")
        self.assertNotIn("BeautifulSoup", source)
        self.assertNotIn("lxml", source)


if __name__ == "__main__":
    unittest.main()
