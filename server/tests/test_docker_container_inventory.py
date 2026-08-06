from types import SimpleNamespace
import unittest
from unittest.mock import patch

from docker import errors

from core import docker_manager as docker_manager_module
from core.docker_manager import DockerManager


class _FakeContainer:
    def __init__(
        self,
        *,
        name: str,
        configured_image: str,
        image_tags=None,
        image_error=None,
    ):
        self.id = f"id-{name}"
        self.name = name
        self.status = "running"
        self.ports = {}
        self.labels = {"test": name}
        self.short_id = self.id[:12]
        self.attrs = {
            "Config": {"Image": configured_image},
            "State": {"Health": {"Status": "healthy"}},
        }
        self._image_tags = image_tags
        self._image_error = image_error

    @property
    def image(self):
        if self._image_error is not None:
            raise self._image_error
        return SimpleNamespace(tags=self._image_tags)


class DockerContainerInventoryTests(unittest.TestCase):
    def test_uninitialized_client_is_not_an_empty_inventory(self):
        manager = object.__new__(DockerManager)
        manager.client = None

        with self.assertRaises(errors.DockerException):
            manager.list_containers(all=True)

    def test_stale_unrelated_image_does_not_hide_runtime_container(self):
        stale_web = _FakeContainer(
            name="hyac-web",
            configured_image="hyac-web-ci:old",
            image_error=errors.NotFound("No such image: stale-manifest"),
        )
        runtime = _FakeContainer(
            name="hyac-app-runtime-app12345",
            configured_image="wicos/hyac_app:release-1",
            image_tags=["wicos/hyac_app:release-1"],
        )
        manager = object.__new__(DockerManager)
        manager.client = SimpleNamespace(
            containers=SimpleNamespace(list=lambda *, all: [stale_web, runtime])
        )

        inventory = manager.list_containers(all=True)

        self.assertEqual(
            [item["name"] for item in inventory],
            ["hyac-web", "hyac-app-runtime-app12345"],
        )
        self.assertEqual(inventory[0]["image"], "hyac-web-ci:old")
        self.assertEqual(inventory[1]["image"], "wicos/hyac_app:release-1")

    def test_non_not_found_image_inspection_failure_is_not_hidden(self):
        unavailable = _FakeContainer(
            name="hyac-web",
            configured_image="hyac-web-ci:old",
            image_error=errors.APIError("Docker daemon unavailable"),
        )
        manager = object.__new__(DockerManager)
        manager.client = SimpleNamespace(
            containers=SimpleNamespace(list=lambda *, all: [unavailable])
        )

        with self.assertRaises(errors.APIError):
            manager.list_containers(all=True)

    def test_top_level_container_list_failure_is_not_an_empty_inventory(self):
        def fail_list(*, all):
            raise errors.APIError("Docker container inventory unavailable")

        manager = object.__new__(DockerManager)
        manager.client = SimpleNamespace(
            containers=SimpleNamespace(list=fail_list)
        )

        with self.assertRaises(errors.APIError):
            manager.list_containers(all=True)

    def test_environment_inspection_api_failure_is_not_hidden(self):
        def fail_get(_name):
            raise errors.APIError("Docker inspect unavailable")

        manager = object.__new__(DockerManager)
        manager.client = SimpleNamespace(
            containers=SimpleNamespace(get=fail_get)
        )

        with self.assertRaises(errors.APIError):
            manager.get_container_environment("runtime-id")

    def test_environment_inspection_not_found_remains_distinct(self):
        def missing_get(_name):
            raise errors.NotFound("runtime disappeared")

        manager = object.__new__(DockerManager)
        manager.client = SimpleNamespace(
            containers=SimpleNamespace(get=missing_get)
        )

        with self.assertRaises(errors.NotFound):
            manager.get_container_environment("runtime-id")


class RuntimeTlsRoutingTests(unittest.TestCase):
    def test_ci_smoke_uses_the_preloaded_certificate_without_acme(self):
        smoke_settings = SimpleNamespace(
            DEV_MODE=False,
            CI_SMOKE_MODE=True,
            RUNTIME_INGRESS_TLS=True,
        )

        with patch.object(docker_manager_module, "settings", smoke_settings):
            self.assertFalse(docker_manager_module._use_acme_certresolver())
            self.assertEqual(
                "      tls: {}",
                docker_manager_module._router_tls_yaml_block(),
            )

    def test_production_tls_keeps_the_acme_resolver(self):
        production_settings = SimpleNamespace(
            DEV_MODE=False,
            CI_SMOKE_MODE=False,
            RUNTIME_INGRESS_TLS=True,
        )

        with patch.object(docker_manager_module, "settings", production_settings):
            self.assertTrue(docker_manager_module._use_acme_certresolver())
            self.assertIn(
                'certResolver: "myresolver"',
                docker_manager_module._router_tls_yaml_block(),
            )


if __name__ == "__main__":
    unittest.main()
