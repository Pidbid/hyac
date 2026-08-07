from pathlib import Path
from unittest import TestCase


ROOT = Path(__file__).resolve().parents[1]
FUNCTION_VIEW = ROOT / "web" / "src" / "views" / "function" / "index.vue"
ZH_LOCALE = ROOT / "web" / "src" / "locales" / "langs" / "zh-cn.ts"
EN_LOCALE = ROOT / "web" / "src" / "locales" / "langs" / "en-us.ts"
APP_TYPINGS = ROOT / "web" / "src" / "typings" / "app.d.ts"


class FunctionSemanticsTest(TestCase):
    def test_workspace_requires_selected_function(self):
        view_source = FUNCTION_VIEW.read_text(encoding="utf-8")

        self.assertIn("const hasSelectedFunction = computed", view_source)
        self.assertIn('v-if="hasSelectedFunction"', view_source)
        self.assertNotIn('v-if="functions.length > 0"', view_source)

    def test_empty_and_unselected_states_have_distinct_copy(self):
        view_source = FUNCTION_VIEW.read_text(encoding="utf-8")
        zh_source = ZH_LOCALE.read_text(encoding="utf-8")
        en_source = EN_LOCALE.read_text(encoding="utf-8")
        typings_source = APP_TYPINGS.read_text(encoding="utf-8")

        self.assertIn("functionWorkspaceDescription", view_source)
        self.assertIn("emptyDescription: '请先创建一个函数'", zh_source)
        self.assertIn("selectFunctionToEdit: '请选择一个函数进行编辑'", zh_source)
        self.assertIn("emptyDescription: 'Create a function first'", en_source)
        self.assertIn("selectFunctionToEdit: 'Select a function to edit'", en_source)
        self.assertIn("selectFunctionToEdit: string", typings_source)
