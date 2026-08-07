"""Shared contract for platform-owned runtime environment variables."""


LEGACY_PLATFORM_ENV_KEYS = frozenset(
    {
        "MONGODB_USERNAME",
        "MONGODB_PASSWORD",
        "SECRET_KEY",
    }
)

RESERVED_ENV_KEYS = frozenset(
    {
        "APP_ID",
        "APP_DB_USERNAME",
        "APP_DB_PASSWORD",
        "RUNTIME_TOKEN",
        "RUNTIME_GENERATION",
        "CONTROL_PLANE_URL",
        "S3_ACCESS_KEY",
        "S3_SECRET_KEY",
        "S3_INTERNAL_ENDPOINT",
        "S3_SECURE_INTERNAL",
        "DEV_MODE",
        "DEBUG",
        "LSP_MODE",
        "LSP_SIDECAR_URL",
        "LSP_SIDECAR_TIMEOUT_SECONDS",
        "LSP_SIDECAR_FALLBACK_LEGACY",
    }
) | LEGACY_PLATFORM_ENV_KEYS


def filter_user_environment_variables(environment_variables):
    """Drop platform-owned keys from a persisted user environment list."""
    return [
        item
        for item in environment_variables
        if (
            item.get("key")
            if isinstance(item, dict)
            else getattr(item, "key", None)
        )
        not in RESERVED_ENV_KEYS
    ]
