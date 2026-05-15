from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
HOME_VIEW = ROOT / "web" / "src" / "views" / "home" / "index.vue"
ZH_LOCALE = ROOT / "web" / "src" / "locales" / "langs" / "zh-cn.ts"
EN_LOCALE = ROOT / "web" / "src" / "locales" / "langs" / "en-us.ts"
APP_TYPINGS = ROOT / "web" / "src" / "typings" / "app.d.ts"


class HomeSemanticsTest(TestCase):
    def test_home_route_represents_applications_entry(self):
        zh_source = ZH_LOCALE.read_text(encoding="utf-8")
        en_source = EN_LOCALE.read_text(encoding="utf-8")

        self.assertIn("home: '应用'", zh_source)
        self.assertIn("home: 'Application'", en_source)

    def test_home_table_title_uses_noun_not_create_action(self):
        view_source = HOME_VIEW.read_text(encoding="utf-8")
        zh_source = ZH_LOCALE.read_text(encoding="utf-8")
        en_source = EN_LOCALE.read_text(encoding="utf-8")
        typings_source = APP_TYPINGS.read_text(encoding="utf-8")

        self.assertIn("page.home.applications", view_source)
        self.assertIn("applications: '应用'", zh_source)
        self.assertIn("applications: 'Application'", en_source)
        self.assertIn("applications: string", typings_source)
