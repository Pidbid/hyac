import json
import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/verify-image-manifest.py"


class ReleaseManifestTests(unittest.TestCase):
    def verify(self, platforms: list[tuple[str, str]]):
        document = {
            "manifests": [
                {"platform": {"os": operating_system, "architecture": architecture}}
                for operating_system, architecture in platforms
            ]
        }
        with tempfile.TemporaryDirectory() as tmp:
            manifest = Path(tmp) / "manifest.json"
            manifest.write_text(json.dumps(document), encoding="utf-8")
            return subprocess.run(
                ["python3", str(SCRIPT), str(manifest)],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )

    def test_accepts_amd64_and_arm64_while_ignoring_attestations(self):
        result = self.verify(
            [("linux", "amd64"), ("linux", "arm64"), ("unknown", "unknown")]
        )
        self.assertEqual(result.returncode, 0, result.stderr)

    def test_rejects_missing_or_unexpected_linux_platforms(self):
        for platforms in (
            [("linux", "amd64")],
            [("linux", "amd64"), ("linux", "arm64"), ("linux", "arm")],
        ):
            with self.subTest(platforms=platforms):
                result = self.verify(platforms)
                self.assertNotEqual(result.returncode, 0)


if __name__ == "__main__":
    unittest.main()
