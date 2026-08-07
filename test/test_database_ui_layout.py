from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
DATABASE_VIEW = ROOT / "web" / "src" / "views" / "database" / "index.vue"
ZH_LOCALE = ROOT / "web" / "src" / "locales" / "langs" / "zh-cn.ts"
EN_LOCALE = ROOT / "web" / "src" / "locales" / "langs" / "en-us.ts"
APP_TYPINGS = ROOT / "web" / "src" / "typings" / "app.d.ts"


class DatabaseUILayoutTest(TestCase):
    def test_right_panel_no_longer_uses_legacy_document_operations_title(self):
        view_source = DATABASE_VIEW.read_text(encoding="utf-8")
        zh_source = ZH_LOCALE.read_text(encoding="utf-8")
        en_source = EN_LOCALE.read_text(encoding="utf-8")
        typings_source = APP_TYPINGS.read_text(encoding="utf-8")

        self.assertNotIn("documentOperations", view_source)
        self.assertNotIn("文档操作", zh_source)
        self.assertNotIn("Document Operations", en_source)
        self.assertNotIn("documentOperations", typings_source)

    def test_right_panel_uses_inspector_toolbar_context(self):
        view_source = DATABASE_VIEW.read_text(encoding="utf-8")

        self.assertIn("class=\"inspector-toolbar\"", view_source)
        self.assertIn("class=\"inspector-tabs\"", view_source)
        self.assertNotIn("class=\"inspector-meta\"", view_source)

    def test_index_table_has_explicit_empty_state_logic(self):
        view_source = DATABASE_VIEW.read_text(encoding="utf-8")
        zh_source = ZH_LOCALE.read_text(encoding="utf-8")
        en_source = EN_LOCALE.read_text(encoding="utf-8")
        typings_source = APP_TYPINGS.read_text(encoding="utf-8")

        self.assertIn('v-if="selectedCollection && indexes.length > 0"', view_source)
        self.assertIn("page.database.noIndexes", view_source)
        self.assertIn("noIndexes: '暂无索引数据'", zh_source)
        self.assertIn("noIndexes: 'No index data'", en_source)
        self.assertIn("noIndexes: string", typings_source)
