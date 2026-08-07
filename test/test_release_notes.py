import subprocess
import tempfile
import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT = REPO_ROOT / "scripts/extract-release-notes.py"


class ReleaseNotesTests(unittest.TestCase):
    def run_extractor(self, tag: str, zh: str, en: str):
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            zh_path = directory / "CHANGELOG.zh-CN.md"
            en_path = directory / "CHANGELOG.md"
            output_path = directory / "release-notes.md"
            zh_path.write_text(zh, encoding="utf-8")
            en_path.write_text(en, encoding="utf-8")

            result = subprocess.run(
                [
                    "python3",
                    str(SCRIPT),
                    "--tag",
                    tag,
                    "--zh",
                    str(zh_path),
                    "--en",
                    str(en_path),
                    "--output",
                    str(output_path),
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                text=True,
                check=False,
            )
            output = output_path.read_text(encoding="utf-8") if output_path.exists() else ""
            return result, output

    def test_extracts_matching_bilingual_sections_in_chinese_first_order(self):
        result, output = self.run_extractor(
            "v1.2.3",
            "# 变更日志\n\n## [v1.2.3] - 2026-08-07\n\n### 新增\n- 发布流水线\n\n## [v1.2.2] - 2026-08-01\n- 旧版本\n",
            "# Changelog\n\n## [v1.2.3] - 2026-08-07\n\n### Added\n- Release pipeline\n\n## [v1.2.2] - 2026-08-01\n- Older release\n",
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            output,
            "## 中文\n\n### 新增\n- 发布流水线\n\n## English\n\n### Added\n- Release pipeline\n",
        )
        self.assertLess(output.index("发布流水线"), output.index("Release pipeline"))
        self.assertNotIn("旧版本", output)
        self.assertNotIn("Older release", output)

    def test_rejects_non_stable_semver_tags(self):
        for tag in ("1.2.3", "v1.2", "v01.2.3", "v1.2.3-rc.1", "dev-1.2.3"):
            with self.subTest(tag=tag):
                result, output = self.run_extractor(
                    tag,
                    f"## [{tag}] - 2026-08-07\n- 中文\n",
                    f"## [{tag}] - 2026-08-07\n- English\n",
                )
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output, "")

    def test_rejects_missing_duplicate_or_empty_sections(self):
        cases = {
            "missing": (
                "## [v1.2.2] - 2026-08-01\n- 旧版本\n",
                "## [v1.2.3] - 2026-08-07\n- Release\n",
            ),
            "duplicate": (
                "## [v1.2.3] - 2026-08-07\n- 一\n\n## [v1.2.3] - 2026-08-08\n- 二\n",
                "## [v1.2.3] - 2026-08-07\n- Release\n",
            ),
            "empty": (
                "## [v1.2.3] - 2026-08-07\n\n## [v1.2.2] - 2026-08-01\n- 旧版本\n",
                "## [v1.2.3] - 2026-08-07\n- Release\n",
            ),
        }
        for name, (zh, en) in cases.items():
            with self.subTest(case=name):
                result, output = self.run_extractor("v1.2.3", zh, en)
                self.assertNotEqual(result.returncode, 0)
                self.assertEqual(output, "")


if __name__ == "__main__":
    unittest.main()
