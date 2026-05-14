import asyncio
import importlib.util
import sys
import types
from pathlib import Path
from enum import Enum
from types import SimpleNamespace
from unittest import TestCase
from unittest.mock import patch


server_path = Path(__file__).resolve().parents[1] / "server"
sys.path.insert(0, str(server_path))

fake_httpx = types.ModuleType("httpx")
fake_httpx.AsyncClient = lambda *args, **kwargs: object()
sys.modules.setdefault("httpx", fake_httpx)

fake_bson = types.ModuleType("bson")
fake_bson.ObjectId = lambda value: value
sys.modules.setdefault("bson", fake_bson)

fake_fastapi = types.ModuleType("fastapi")


class FakeAPIRouter:
    def __init__(self, *args, **kwargs):
        pass

    def post(self, *args, **kwargs):
        return lambda func: func


class FakeHTTPException(Exception):
    def __init__(self, status_code, detail=None):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


fake_fastapi.APIRouter = FakeAPIRouter
fake_fastapi.Depends = lambda dependency=None: dependency
fake_fastapi.HTTPException = FakeHTTPException
fake_fastapi.Response = object
sys.modules.setdefault("fastapi", fake_fastapi)

fake_loguru = types.ModuleType("loguru")
fake_loguru.logger = object()
sys.modules.setdefault("loguru", fake_loguru)

fake_pydantic = types.ModuleType("pydantic")


class FakeBaseModel:
    def __init__(self, **kwargs):
        annotations = getattr(type(self), "__annotations__", {})
        for name in annotations:
            if name in kwargs:
                value = kwargs[name]
            else:
                value = getattr(type(self), name, None)
            setattr(self, name, value)


def fake_field(default=None, **kwargs):
    if "default_factory" in kwargs:
        return kwargs["default_factory"]()
    return default


fake_pydantic.BaseModel = FakeBaseModel
fake_pydantic.Field = fake_field
sys.modules.setdefault("pydantic", fake_pydantic)

fake_core_beanie = types.ModuleType("core.beanie_compat")
fake_core_beanie.aggregate_to_list = object
sys.modules.setdefault("core.beanie_compat", fake_core_beanie)

fake_core_config = types.ModuleType("core.config")
fake_core_config.settings = SimpleNamespace(DOMAIN_NAME="example.com")
sys.modules.setdefault("core.config", fake_core_config)

fake_core_jwt = types.ModuleType("core.jwt_auth")
fake_core_jwt.get_current_user = lambda: None
sys.modules.setdefault("core.jwt_auth", fake_core_jwt)


class FakeBaseResponse:
    def __init__(self, code=0, msg="", data=None):
        self.code = code
        self.msg = msg
        self.data = data


class FakeFunctionType(str, Enum):
    ENDPOINT = "endpoint"
    COMMON = "common"


class FakeFunctionStatus(str, Enum):
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"


for module_name, attrs in {
    "models.applications_model": {"Application": object},
    "models.common_model": {"BaseResponse": FakeBaseResponse},
    "models.functions_history_model": {"FunctionsHistory": object},
    "models.functions_model": {
        "Function": object,
        "FunctionStatus": FakeFunctionStatus,
        "FunctionType": FakeFunctionType,
    },
    "models.function_template_model": {"FunctionTemplate": object},
    "models.statistics_model": {"FunctionMetric": object},
    "models.users_model": {"User": object},
}.items():
    module = types.ModuleType(module_name)
    for key, value in attrs.items():
        setattr(module, key, value)
    sys.modules[module_name] = module

functions_path = server_path / "routers" / "functions.py"
spec = importlib.util.spec_from_file_location("hyac_functions_router_for_test", functions_path)
functions_router = importlib.util.module_from_spec(spec)
assert spec and spec.loader
spec.loader.exec_module(functions_router)


class FieldExpression:
    def __init__(self, name):
        self.name = name

    def __eq__(self, other):
        return (self.name, other)


class FakeApplication:
    app_id = FieldExpression("app_id")
    users = FieldExpression("users")
    result = None

    @classmethod
    async def find_one(cls, *conditions):
        cls.conditions = conditions
        return cls.result


class FakeFunction:
    function_name = FieldExpression("function_name")
    app_id = FieldExpression("app_id")
    inserted = None
    existing = None

    def __init__(self, **kwargs):
        self.__dict__.update(kwargs)
        self.function_id = "created-function"

    @classmethod
    async def find_one(cls, *conditions):
        cls.conditions = conditions
        return cls.existing

    async def insert(self):
        type(self).inserted = self


class FakeFunctionTemplate:
    id = FieldExpression("id")
    app_id = FieldExpression("app_id")
    type = FieldExpression("type")
    function_type = FieldExpression("function_type")
    result = None
    calls = []

    @classmethod
    async def find_one(cls, *conditions):
        cls.calls.append(conditions)
        return cls.result


class FunctionTemplateSelectionTest(TestCase):
    def setUp(self):
        FakeApplication.result = SimpleNamespace(app_id="app-a")
        FakeFunction.existing = None
        FakeFunction.inserted = None
        FakeFunctionTemplate.result = SimpleNamespace(
            app_id="app-a",
            shared=False,
            function_type=functions_router.FunctionType.ENDPOINT,
            code="async def handler(ctx, request):\n    return {'ok': True}",
        )
        FakeFunctionTemplate.calls = []

    def run_create(self, template_id=None):
        data = functions_router.CreateFunctionRequest(
            appId="app-a",
            name="hello",
            type="endpoint",
            template_id=template_id,
        )
        current_user = SimpleNamespace(username="alice")

        with (
            patch.object(functions_router, "Application", FakeApplication),
            patch.object(functions_router, "Function", FakeFunction),
            patch.object(functions_router, "FunctionTemplate", FakeFunctionTemplate),
        ):
            return asyncio.run(functions_router.create_function(data, current_user))

    def test_default_system_template_query_is_scoped_to_current_app(self):
        response = self.run_create()

        self.assertEqual(response.code, 0)
        conditions = FakeFunctionTemplate.calls[-1]
        self.assertIn(("app_id", "app-a"), conditions)
        self.assertIn(("type", "system"), conditions)

    def test_rejects_private_template_from_another_app(self):
        FakeFunctionTemplate.result = SimpleNamespace(
            app_id="other-app",
            shared=False,
            function_type=functions_router.FunctionType.ENDPOINT,
            code="async def handler(ctx, request):\n    return {'ok': True}",
        )

        with self.assertRaises(functions_router.HTTPException) as exc:
            self.run_create(template_id="507f1f77bcf86cd799439011")

        self.assertEqual(exc.exception.status_code, 403)

    def test_allows_shared_template_from_another_app(self):
        FakeFunctionTemplate.result = SimpleNamespace(
            app_id="other-app",
            shared=True,
            function_type=functions_router.FunctionType.ENDPOINT,
            code="async def handler(ctx, request):\n    return {'ok': True}",
        )

        response = self.run_create(template_id="507f1f77bcf86cd799439011")

        self.assertEqual(response.code, 0)
