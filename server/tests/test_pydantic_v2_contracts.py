import os
import subprocess
import sys
import tempfile
from pathlib import Path
from unittest import TestCase
from unittest.mock import patch


os.environ.setdefault("DEV_MODE", "true")

from core.config import Settings
from models.scheduled_tasks_model import ScheduledTask
from models.tasks_model import Task


class PydanticV2ContractTests(TestCase):
    def test_server_models_import_without_pydantic_v2_deprecation_warnings(self):
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                (
                    "import warnings; "
                    "from pydantic.warnings import PydanticDeprecatedSince20; "
                    "warnings.simplefilter('error', PydanticDeprecatedSince20); "
                    "import core.config; "
                    "import models.scheduled_tasks_model; "
                    "import models.tasks_model; "
                    "import routers.users"
                ),
            ],
            check=False,
            capture_output=True,
            text=True,
            env={**os.environ, "DEV_MODE": "true"},
        )

        self.assertEqual(0, result.returncode, result.stderr)

    def test_scheduled_task_schema_example_is_preserved(self):
        self.assertEqual(
            {
                "function_id": "func_12345678",
                "name": "Example Cron Job",
                "trigger": "cron",
                "trigger_config": {"minute": "*/1"},
                "params": {"query": "test"},
                "body": {"key": "value"},
                "enabled": True,
                "description": "This is an example cron job that runs every minute.",
            },
            ScheduledTask.model_json_schema()["example"],
        )

    def test_server_settings_ignore_dotenv_and_keep_case_sensitive_environment(self):
        with tempfile.TemporaryDirectory() as directory:
            Path(directory, ".env").write_text(
                "DEV_MODE=false\nSECRET_KEY=dotenv-secret\n", encoding="utf-8"
            )
            previous_directory = os.getcwd()
            try:
                os.chdir(directory)
                with patch.dict(
                    os.environ,
                    {"DEV_MODE": "true", "secret_key": "lowercase-secret"},
                    clear=True,
                ):
                    settings = Settings()
            finally:
                os.chdir(previous_directory)

        self.assertTrue(settings.DEV_MODE)
        self.assertIsNone(settings.SECRET_KEY)

    def test_document_indexes_are_explicit_and_field_extras_are_removed(self):
        self.assertIsNone(Task.model_fields["task_id"].json_schema_extra)
        for field_name in ("task_id", "app_id", "function_id"):
            with self.subTest(field_name=field_name):
                self.assertIsNone(
                    ScheduledTask.model_fields[field_name].json_schema_extra
                )

        indexes = [index.document for index in ScheduledTask.Settings.indexes]
        self.assertEqual(
            [
                {"unique": True, "name": "task_id_1", "key": {"task_id": 1}},
                {"name": "app_id_1", "key": {"app_id": 1}},
                {"name": "function_id_1", "key": {"function_id": 1}},
            ],
            indexes,
        )
