import importlib.util
from pathlib import Path
from unittest import TestCase


faas_code_path = Path(__file__).resolve().parents[1] / "server" / "core" / "faas_code.py"
spec = importlib.util.spec_from_file_location("hyac_faas_code_for_test", faas_code_path)
faas_code = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(faas_code)


class FaasTemplatesCloudFacadeTest(TestCase):
    def test_default_templates_prefer_cloud_facade(self):
        self.assertIn("ctx.cloud.logger()", faas_code.endpoint_template_get)
        self.assertIn("ctx.cloud.database()", faas_code.endpoint_template_db)
        self.assertIn("ctx.cloud.database(sync=True)", faas_code.endpoint_template_db)
        self.assertIn("ctx.cloud.storage()", faas_code.endpoint_template_storage)
        self.assertIn("ctx.cloud.notification()", faas_code.endpoint_template_notification)

    def test_storage_template_handles_cloud_facade_failure_results(self):
        self.assertIn("write_ok = await storage.put", faas_code.endpoint_template_storage)
        self.assertIn("if not write_ok:", faas_code.endpoint_template_storage)
        self.assertIn("if data is None:", faas_code.endpoint_template_storage)

    def test_pydantic_template_uses_cloud_facade_logger_and_database_comment(self):
        self.assertIn("logger = ctx.cloud.logger()", faas_code.endpoint_template_pydantic)
        self.assertIn("ctx.cloud.database()", faas_code.endpoint_template_pydantic)
        self.assertNotIn("ctx.async_db", faas_code.endpoint_template_pydantic)

    def test_common_call_template_uses_cloud_facade_common_namespace(self):
        self.assertIn("common = ctx.cloud.common()", faas_code.endpoint_template_common_call)
        self.assertNotIn("ctx.common", faas_code.endpoint_template_common_call)
