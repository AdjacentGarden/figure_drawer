from __future__ import annotations

import importlib.util
import json
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SKILL = ROOT / "skills" / "research-figure-drawer"


def load_module(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, path)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader
    spec.loader.exec_module(module)
    return module


class VendoredRuntimeTests(unittest.TestCase):
    def test_vendored_files_match_recorded_hashes(self):
        module = load_module("check_environment", SKILL / "scripts" / "check_environment.py")
        result = module.verify_vendor_manifest()
        self.assertTrue(result["ok"], result["problems"])
        self.assertGreaterEqual(result["checked"], 30)

    def test_manifest_pins_upstream_source_and_license(self):
        manifest = json.loads((SKILL / "cli" / "VENDOR.json").read_text(encoding="utf-8"))
        self.assertEqual(manifest["component"], "image-to-editable-ppt")
        self.assertEqual(
            manifest["upstream_repository"],
            "https://github.com/ningzimu/image-to-editable-ppt-skill",
        )
        self.assertRegex(manifest["upstream_commit"], r"^[0-9a-f]{40}$")
        self.assertEqual(manifest["license"], "MIT")
        self.assertEqual(manifest["file_count"], len(manifest["files"]))

    def test_upstream_license_text_is_redistributed(self):
        # The MIT terms require the copyright and permission notice to ship with the code.
        license_text = (SKILL / "cli" / "LICENSE").read_text(encoding="utf-8")
        self.assertIn("MIT License", license_text)
        self.assertIn("Copyright (c) 2026 ningzimu", license_text)
        self.assertIn("permission notice shall be included", license_text)
        notices = (ROOT / "THIRD_PARTY_NOTICES.md").read_text(encoding="utf-8")
        self.assertIn("ningzimu/image-to-editable-ppt-skill", notices)
        self.assertIn("Copyright (c) 2026 ningzimu", notices)
        self.assertIn("cli/LICENSE", notices)

    def test_bundled_runtime_and_launcher_are_present(self):
        self.assertTrue((SKILL / "cli" / "pyproject.toml").is_file())
        self.assertTrue((SKILL / "cli" / "editppt" / "cli.py").is_file())
        self.assertTrue((SKILL / "scripts" / "run_editppt.py").is_file())
        self.assertTrue((SKILL / "prompts" / "page-worker.md").is_file())
        self.assertTrue((SKILL / "scripts" / "build-page-worker-prompt.py").is_file())

    def test_vendored_contract_keeps_upstream_body_and_provenance(self):
        contract = (SKILL / "references" / "reconstruction-contract.md").read_text(encoding="utf-8")
        self.assertIn("Vendored copy. Do not edit in place.", contract)
        self.assertIn("b7be494e31a0ed56ef98716891db5474606b8cdf", contract)
        self.assertIn("# Image to Editable PPT", contract)

    def test_skill_no_longer_requires_a_second_installed_skill(self):
        skill_md = (SKILL / "SKILL.md").read_text(encoding="utf-8")
        self.assertNotIn("npx -y skills@latest add ningzimu", skill_md)
        self.assertNotIn("Require the `image-to-editable-ppt` skill", skill_md)
        self.assertNotIn("dependency skill", skill_md)
        installed_hint = "skills/image-to-editable-ppt"
        for path in (
            SKILL / "SKILL.md",
            SKILL / "references" / "installation.md",
            SKILL / "scripts" / "check_environment.py",
        ):
            self.assertNotIn(installed_hint, path.read_text(encoding="utf-8"), path.name)


if __name__ == "__main__":
    unittest.main()
