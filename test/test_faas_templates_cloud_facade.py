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

    def test_post_template_documents_the_isolated_request_snapshot_contract(self):
        template = faas_code.endpoint_template_post

        self.assertNotIn("full control", template.lower())
        self.assertIn(
            "available: method, url/path, query_params, headers, client, server,",
            template,
        )
        self.assertIn(
            "path_params, and the bounded body via request.body() or request.json()",
            template,
        )
        self.assertIn(
            "unavailable: request.app, request.state, request.url_for()/router,",
            template,
        )
        self.assertIn(
            "request.session, request.auth, request.user, live request.stream(),",
            template,
        )
        self.assertIn("real-time client-disconnect events", template)

    def test_background_template_documents_isolated_completion_contract(self):
        template = faas_code.endpoint_template_background

        self.assertNotIn("returned to the client immediately", template)
        self.assertNotIn("after the response has been sent", template)
        self.assertIn(
            "runs BackgroundTasks items in registration order before returning the result",
            template,
        )
        self.assertIn("Task time counts against the function timeout", template)
        self.assertIn(
            "a timeout terminates the invocation\n    without returning the buffered result",
            template,
        )
        self.assertIn("The first task failure is written to the", template)
        self.assertIn("function logs, skips remaining items", template)
        self.assertIn(
            "does not replace a successful result\n    that has already been buffered",
            template,
        )
