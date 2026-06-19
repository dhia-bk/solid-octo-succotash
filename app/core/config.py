"""
Runtime configuration entrypoint for Project Pulse Knowledge Graph.

Loading order:
1. configs/base.yaml
2. selected environment overlay (dev.yaml / staging.yaml / prod.yaml)
3. standalone config files:
   - logging.yaml
   - ontology.yaml
   - weighting.yaml
   - inference.yaml
   - gds.yaml
   - source_inclusion.yaml
   - serving.yaml
4. environment variable overrides
5. typed validation
6. cached singleton access via get_settings()

Design rules:
- No later module should read YAML directly.
- All config access should go through get_settings().
- All internal config objects should be typed.
"""

from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from app.core.constants import (
    CONFIG_SECTION_API,
    CONFIG_SECTION_APP,
    CONFIG_SECTION_CHECKPOINTS,
    CONFIG_SECTION_GDS,
    CONFIG_SECTION_INFERENCE,
    CONFIG_SECTION_METADATA_DB,
    CONFIG_SECTION_MYSQL,
    CONFIG_SECTION_NEO4J,
    CONFIG_SECTION_OBSERVABILITY,
    CONFIG_SECTION_PIPELINES,
    CONFIG_SECTION_RUNTIME,
    CONFIG_SECTION_SCHEDULER,
    CONFIG_SECTION_SECURITY,
    CONFIG_SECTION_SERVING,
    CONFIG_SECTION_SOURCE_INCLUSION,
    CONFIG_SECTION_WEIGHTING,
    DEFAULT_APP_NAME,
    DEFAULT_BATCH_SIZE,
    DEFAULT_CHECKPOINT_NAMESPACE,
    DEFAULT_MAX_RETRIES,
    DEFAULT_TIMEZONE,
    DEV,
    MAX_BATCH_SIZE,
    PROD,
    STAGING,
    AppEnv,
)
from app.core.exceptions import ConfigurationError, InvalidConfigError, InvalidEnvironmentError
from app.core.logging import get_logger
from app.core.security import (
    build_safe_startup_config_summary,
    get_optional_env,
    get_optional_env_bool,
    get_optional_env_int,
    sanitize_config_payload,
)

logger = get_logger(__name__)


CONFIG_SECTION_ONTOLOGY_CANONICAL = "ontology"

SUPPORTED_ENVS: tuple[str, ...] = (DEV, STAGING, PROD)


# Pydantic models


class AppSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    name: str = DEFAULT_APP_NAME
    env: AppEnv = DEV
    debug: bool = False
    timezone: str = DEFAULT_TIMEZONE


class CorsSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = False
    allow_origins: list[str] = Field(default_factory=list)
    allow_methods: list[str] = Field(default_factory=list)
    allow_headers: list[str] = Field(default_factory=list)


class ApiSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    host: str = "0.0.0.0"
    port: int = 8000
    version: str = "v1"
    cors: CorsSettings = Field(default_factory=CorsSettings)

    @field_validator("port")
    @classmethod
    def validate_port(cls, value: int) -> int:
        if value <= 0 or value > 65535:
            raise InvalidConfigError("API port must be between 1 and 65535", port=value)
        return value


class SecuritySettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    api_key_enabled: bool = False
    api_key_header: str = "X-API-Key"
    mask_secrets_in_logs: bool = True


class RuntimeSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    max_retries: int = DEFAULT_MAX_RETRIES
    retry_backoff_seconds: int = 2
    default_batch_size: int = DEFAULT_BATCH_SIZE
    max_batch_size: int = MAX_BATCH_SIZE
    fail_fast: bool = True

    @model_validator(mode="after")
    def validate_runtime(self) -> RuntimeSettings:
        if self.default_batch_size <= 0:
            raise InvalidConfigError(
                "default_batch_size must be positive",
                default_batch_size=self.default_batch_size,
            )
        if self.max_batch_size <= 0:
            raise InvalidConfigError(
                "max_batch_size must be positive",
                max_batch_size=self.max_batch_size,
            )
        if self.default_batch_size > self.max_batch_size:
            raise InvalidConfigError(
                "default_batch_size cannot exceed max_batch_size",
                default_batch_size=self.default_batch_size,
                max_batch_size=self.max_batch_size,
            )
        if self.max_retries < 0:
            raise InvalidConfigError("max_retries cannot be negative", max_retries=self.max_retries)
        if self.retry_backoff_seconds < 0:
            raise InvalidConfigError(
                "retry_backoff_seconds cannot be negative",
                retry_backoff_seconds=self.retry_backoff_seconds,
            )
        return self


class PipelinesSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    full_backfill_enabled: bool = True
    incremental_sync_enabled: bool = True
    serving_materialization_enabled: bool = True
    source_inventory_audit_enabled: bool = True


class CheckpointsSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    namespace: str = DEFAULT_CHECKPOINT_NAMESPACE
    strategy: str = "timestamp_watermark"

    @field_validator("namespace")
    @classmethod
    def validate_namespace(cls, value: str) -> str:
        if not value.strip():
            raise InvalidConfigError("Checkpoint namespace cannot be blank")
        return value.strip()


class MySQLSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    host: str
    port: int = 3306
    db: str
    user: str
    password: str
    connect_timeout: int = 10
    read_timeout: int = 60
    write_timeout: int = 60
    pool_size: int = 5
    max_overflow: int = 10

    @model_validator(mode="after")
    def validate_mysql(self) -> MySQLSettings:
        for field_name in ("host", "db", "user", "password"):
            if not getattr(self, field_name) or not str(getattr(self, field_name)).strip():
                raise InvalidConfigError(
                    "MySQL configuration field cannot be empty",
                    field_name=field_name,
                )
        if self.port <= 0 or self.port > 65535:
            raise InvalidConfigError("MySQL port must be between 1 and 65535", port=self.port)
        return self


class Neo4jSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    uri: str
    user: str
    password: str
    database: str = "neo4j"
    fetch_size: int = 1000
    max_connection_lifetime_seconds: int = 3600
    connection_acquisition_timeout_seconds: int = 30

    @model_validator(mode="after")
    def validate_neo4j(self) -> Neo4jSettings:
        for field_name in ("uri", "user", "password", "database"):
            if not getattr(self, field_name) or not str(getattr(self, field_name)).strip():
                raise InvalidConfigError(
                    "Neo4j configuration field cannot be empty",
                    field_name=field_name,
                )
        return self


class MetadataDBSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    host: str
    port: int = 3306
    name: str
    user: str
    password: str
    pool_size: int = 5
    max_overflow: int = 10

    @model_validator(mode="after")
    def validate_metadata_db(self) -> MetadataDBSettings:
        for field_name in ("host", "name", "user", "password"):
            if not getattr(self, field_name) or not str(getattr(self, field_name)).strip():
                raise InvalidConfigError(
                    "Metadata DB configuration field cannot be empty",
                    field_name=field_name,
                )
        if self.port <= 0 or self.port > 65535:
            raise InvalidConfigError(
                "Metadata DB port must be between 1 and 65535",
                port=self.port,
            )
        return self


class ObservabilitySettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    metrics_enabled: bool = True
    tracing_enabled: bool = False
    healthcheck_enabled: bool = True


class SchedulerSettings(BaseModel):
    model_config = ConfigDict(extra="ignore")

    enabled: bool = True
    timezone: str = DEFAULT_TIMEZONE


class RootSettings(BaseModel):
    """
    Strongly typed runtime settings object.
    """

    model_config = ConfigDict(extra="ignore")

    app: AppSettings
    api: ApiSettings
    security: SecuritySettings
    runtime: RuntimeSettings
    pipelines: PipelinesSettings
    checkpoints: CheckpointsSettings
    mysql: MySQLSettings
    neo4j: Neo4jSettings
    metadata_db: MetadataDBSettings
    observability: ObservabilitySettings
    scheduler: SchedulerSettings

    logging: dict[str, Any] = Field(default_factory=dict)
    ontology: dict[str, Any] = Field(default_factory=dict)
    weighting: dict[str, Any] = Field(default_factory=dict)
    inference: dict[str, Any] = Field(default_factory=dict)
    gds: dict[str, Any] = Field(default_factory=dict)
    source_inclusion: dict[str, Any] = Field(default_factory=dict)
    serving: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def validate_root(self) -> RootSettings:
        if self.app.env not in SUPPORTED_ENVS:
            raise InvalidEnvironmentError(
                "Unsupported environment",
                env=self.app.env,
                supported=SUPPORTED_ENVS,
            )
        return self

    def sanitized_summary(self) -> dict[str, Any]:
        """
        Return a secret-safe config summary suitable for startup logs.
        """
        return build_safe_startup_config_summary(
            app=self.app.model_dump(),
            api=self.api.model_dump(),
            mysql=self.mysql.model_dump(),
            neo4j=self.neo4j.model_dump(),
            metadata_db=self.metadata_db.model_dump(),
            security=self.security.model_dump(),
            runtime=self.runtime.model_dump(),
        )


# YAML loading and merging


def _read_yaml_file(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigurationError(
            "Configuration file does not exist",
            config_path=str(path),
        )

    try:
        with path.open("r", encoding="utf-8") as handle:
            loaded = yaml.safe_load(handle) or {}
    except OSError as exc:
        raise ConfigurationError(
            "Failed to read configuration file",
            config_path=str(path),
        ) from exc
    except yaml.YAMLError as exc:
        raise ConfigurationError(
            "Invalid YAML configuration",
            config_path=str(path),
        ) from exc

    if not isinstance(loaded, dict):
        raise ConfigurationError(
            "Configuration file root must be a mapping",
            config_path=str(path),
        )

    return loaded


def _deep_merge(base: dict[str, Any], overlay: dict[str, Any]) -> dict[str, Any]:
    """
    Deep merge overlay into base, returning a new dict.
    """
    merged = dict(base)

    for key, overlay_value in overlay.items():
        base_value = merged.get(key)
        if isinstance(base_value, dict) and isinstance(overlay_value, dict):
            merged[key] = _deep_merge(base_value, overlay_value)
        else:
            merged[key] = overlay_value

    return merged


# Config path resolution


def _resolve_config_dir() -> Path:
    """
    Resolve config directory from environment or project default.
    """
    raw = get_optional_env("CONFIG_DIR", default="./configs")
    if raw is None:
        raise ConfigurationError("CONFIG_DIR could not be resolved")

    path = Path(raw).expanduser().resolve()

    if not path.exists() or not path.is_dir():
        raise ConfigurationError(
            "CONFIG_DIR does not exist or is not a directory",
            config_dir=str(path),
        )

    return path


def _resolve_runtime_env() -> str:
    """
    Resolve requested runtime environment.
    """
    env_name = get_optional_env("APP_ENV", default=DEV)
    if env_name is None:
        raise ConfigurationError("APP_ENV could not be resolved")

    env_name = env_name.strip().lower()
    if env_name not in SUPPORTED_ENVS:
        raise InvalidEnvironmentError(
            "Unsupported environment",
            env=env_name,
            supported=SUPPORTED_ENVS,
        )
    return env_name


# Standalone config file loading


def _load_core_yaml_bundle(config_dir: Path, env_name: str) -> dict[str, Any]:
    """
    Load base.yaml and environment overlay, then merge them.
    """
    base_config = _read_yaml_file(config_dir / "base.yaml")
    env_config = _read_yaml_file(config_dir / f"{env_name}.yaml")

    merged = _deep_merge(base_config, env_config)

    return merged


def _load_standalone_configs(config_dir: Path) -> dict[str, Any]:
    """
    Load standalone config files and return them as named sections.
    """
    standalone_map = {
        "logging": "logging.yaml",
        CONFIG_SECTION_ONTOLOGY_CANONICAL: "ontology.yaml",
        CONFIG_SECTION_WEIGHTING: "weighting.yaml",
        CONFIG_SECTION_INFERENCE: "inference.yaml",
        CONFIG_SECTION_GDS: "gds.yaml",
        CONFIG_SECTION_SOURCE_INCLUSION: "source_inclusion.yaml",
        CONFIG_SECTION_SERVING: "serving.yaml",
    }

    loaded: dict[str, Any] = {}
    for section_name, filename in standalone_map.items():
        loaded[section_name] = _read_yaml_file(config_dir / filename)

    return loaded


# Environment variable overrides


def _set_if_not_none(payload: dict[str, Any], section: str, key: str, value: Any) -> None:
    if value is None:
        return
    payload.setdefault(section, {})
    payload[section][key] = value


def _apply_env_overrides(config: dict[str, Any]) -> dict[str, Any]:
    """
    Apply env var overrides on top of merged YAML config.
    """
    updated = dict(config)

    # App / API
    _set_if_not_none(updated, CONFIG_SECTION_APP, "name", get_optional_env("APP_NAME"))
    _set_if_not_none(updated, CONFIG_SECTION_APP, "env", get_optional_env("APP_ENV"))
    _set_if_not_none(updated, CONFIG_SECTION_APP, "debug", get_optional_env_bool("APP_DEBUG"))

    _set_if_not_none(updated, CONFIG_SECTION_API, "host", get_optional_env("APP_HOST"))
    _set_if_not_none(updated, CONFIG_SECTION_API, "port", get_optional_env_int("APP_PORT"))

    # Security
    _set_if_not_none(
        updated,
        CONFIG_SECTION_SECURITY,
        "api_key_enabled",
        get_optional_env_bool("API_KEY_ENABLED"),
    )
    _set_if_not_none(
        updated,
        CONFIG_SECTION_SECURITY,
        "api_key_header",
        get_optional_env("API_KEY_HEADER"),
    )
    _set_if_not_none(
        updated,
        CONFIG_SECTION_SECURITY,
        "api_key_value",
        get_optional_env("API_KEY_VALUE"),
    )

    # Runtime
    _set_if_not_none(
        updated,
        CONFIG_SECTION_RUNTIME,
        "default_batch_size",
        get_optional_env_int("DEFAULT_BATCH_SIZE"),
    )
    _set_if_not_none(
        updated,
        CONFIG_SECTION_RUNTIME,
        "max_retries",
        get_optional_env_int("MAX_RETRIES"),
    )

    # Checkpoints
    _set_if_not_none(
        updated,
        CONFIG_SECTION_CHECKPOINTS,
        "namespace",
        get_optional_env("CHECKPOINT_NAMESPACE"),
    )

    # MySQL
    _set_if_not_none(updated, CONFIG_SECTION_MYSQL, "host", get_optional_env("MYSQL_HOST"))
    _set_if_not_none(updated, CONFIG_SECTION_MYSQL, "port", get_optional_env_int("MYSQL_PORT"))
    _set_if_not_none(updated, CONFIG_SECTION_MYSQL, "db", get_optional_env("MYSQL_DB"))
    _set_if_not_none(updated, CONFIG_SECTION_MYSQL, "user", get_optional_env("MYSQL_USER"))
    _set_if_not_none(
        updated,
        CONFIG_SECTION_MYSQL,
        "password",
        get_optional_env("MYSQL_PASSWORD"),
    )
    _set_if_not_none(
        updated,
        CONFIG_SECTION_MYSQL,
        "connect_timeout",
        get_optional_env_int("MYSQL_CONNECT_TIMEOUT"),
    )

    # Neo4j
    _set_if_not_none(updated, CONFIG_SECTION_NEO4J, "uri", get_optional_env("NEO4J_URI"))
    _set_if_not_none(updated, CONFIG_SECTION_NEO4J, "user", get_optional_env("NEO4J_USER"))
    _set_if_not_none(
        updated,
        CONFIG_SECTION_NEO4J,
        "password",
        get_optional_env("NEO4J_PASSWORD"),
    )
    _set_if_not_none(
        updated,
        CONFIG_SECTION_NEO4J,
        "database",
        get_optional_env("NEO4J_DATABASE"),
    )

    # Metadata DB
    _set_if_not_none(
        updated,
        CONFIG_SECTION_METADATA_DB,
        "host",
        get_optional_env("METADATA_DB_HOST"),
    )
    _set_if_not_none(
        updated,
        CONFIG_SECTION_METADATA_DB,
        "port",
        get_optional_env_int("METADATA_DB_PORT"),
    )
    _set_if_not_none(
        updated,
        CONFIG_SECTION_METADATA_DB,
        "name",
        get_optional_env("METADATA_DB_NAME"),
    )
    _set_if_not_none(
        updated,
        CONFIG_SECTION_METADATA_DB,
        "user",
        get_optional_env("METADATA_DB_USER"),
    )
    _set_if_not_none(
        updated,
        CONFIG_SECTION_METADATA_DB,
        "password",
        get_optional_env("METADATA_DB_PASSWORD"),
    )

    # Pipelines
    _set_if_not_none(
        updated,
        CONFIG_SECTION_PIPELINES,
        "full_backfill_enabled",
        get_optional_env_bool("FULL_BACKFILL_ENABLED"),
    )
    _set_if_not_none(
        updated,
        CONFIG_SECTION_PIPELINES,
        "incremental_sync_enabled",
        get_optional_env_bool("INCREMENTAL_SYNC_ENABLED"),
    )

    # Observability
    _set_if_not_none(
        updated,
        CONFIG_SECTION_OBSERVABILITY,
        "metrics_enabled",
        get_optional_env_bool("METRICS_ENABLED"),
    )
    _set_if_not_none(
        updated,
        CONFIG_SECTION_OBSERVABILITY,
        "tracing_enabled",
        get_optional_env_bool("TRACING_ENABLED"),
    )

    # Scheduler
    _set_if_not_none(
        updated,
        CONFIG_SECTION_SCHEDULER,
        "enabled",
        get_optional_env_bool("SCHEDULER_ENABLED"),
    )

    # GDS specific convenience overrides
    gds_section = updated.setdefault(CONFIG_SECTION_GDS, {})
    gds_payload = gds_section.setdefault("gds", {})
    projection_payload = gds_payload.setdefault("projection", {})
    leiden_payload = gds_payload.setdefault("leiden", {})
    membership_filter_payload = gds_payload.setdefault("membership_filter", {})

    graph_name = get_optional_env("LEIDEN_GRAPH_NAME")
    if graph_name is not None:
        projection_payload["graph_name"] = graph_name

    leiden_write_property = get_optional_env("LEIDEN_WRITE_PROPERTY")
    if leiden_write_property is not None:
        leiden_payload["write_property"] = leiden_write_property

    weight_threshold = get_optional_env("LEIDEN_WEIGHT_THRESHOLD")
    if weight_threshold is not None:
        try:
            membership_filter_payload["activity_weight_min"] = float(weight_threshold)
        except ValueError as exc:
            raise InvalidConfigError(
                "LEIDEN_WEIGHT_THRESHOLD must be a valid float",
                raw_value=weight_threshold,
            ) from exc

    return updated


# Typed model conversion


def _build_settings_model(merged: dict[str, Any]) -> RootSettings:
    """
    Convert merged config dict into typed settings.
    """
    try:
        settings = RootSettings(
            app=AppSettings.model_validate(merged.get(CONFIG_SECTION_APP, {})),
            api=ApiSettings.model_validate(merged.get(CONFIG_SECTION_API, {})),
            security=SecuritySettings.model_validate(merged.get(CONFIG_SECTION_SECURITY, {})),
            runtime=RuntimeSettings.model_validate(merged.get(CONFIG_SECTION_RUNTIME, {})),
            pipelines=PipelinesSettings.model_validate(merged.get(CONFIG_SECTION_PIPELINES, {})),
            checkpoints=CheckpointsSettings.model_validate(
                merged.get(CONFIG_SECTION_CHECKPOINTS, {})
            ),
            mysql=MySQLSettings.model_validate(merged.get(CONFIG_SECTION_MYSQL, {})),
            neo4j=Neo4jSettings.model_validate(merged.get(CONFIG_SECTION_NEO4J, {})),
            metadata_db=MetadataDBSettings.model_validate(
                merged.get(CONFIG_SECTION_METADATA_DB, {})
            ),
            observability=ObservabilitySettings.model_validate(
                merged.get(CONFIG_SECTION_OBSERVABILITY, {})
            ),
            scheduler=SchedulerSettings.model_validate(merged.get(CONFIG_SECTION_SCHEDULER, {})),
            logging=merged.get("logging", {}),
            ontology=merged.get(CONFIG_SECTION_ONTOLOGY_CANONICAL, {}),
            weighting=merged.get(CONFIG_SECTION_WEIGHTING, {}),
            inference=merged.get(CONFIG_SECTION_INFERENCE, {}),
            gds=merged.get(CONFIG_SECTION_GDS, {}),
            source_inclusion=merged.get(CONFIG_SECTION_SOURCE_INCLUSION, {}),
            serving=merged.get(CONFIG_SECTION_SERVING, {}),
        )
    except Exception as exc:  # noqa: BLE001
        raise InvalidConfigError(
            "Failed to validate runtime configuration",
            error_type=type(exc).__name__,
            error_message=str(exc),
        ) from exc

    return settings


# Public loading interface


def load_settings() -> RootSettings:
    """
    Load, merge, validate, and return runtime settings.

    This function is deterministic and should be the only path by which YAML
    configuration becomes typed runtime settings.
    """
    config_dir = _resolve_config_dir()
    env_name = _resolve_runtime_env()

    core_bundle = _load_core_yaml_bundle(config_dir, env_name)
    standalone_bundle = _load_standalone_configs(config_dir)

    merged = _deep_merge(core_bundle, standalone_bundle)
    merged = _apply_env_overrides(merged)

    settings = _build_settings_model(merged)

    logger.info(
        "Runtime settings loaded successfully",
        extra={
            "config_dir": str(config_dir),
            "env": settings.app.env,
        },
    )

    return settings


@lru_cache(maxsize=1)
def get_settings() -> RootSettings:
    """
    Return cached singleton runtime settings.
    """
    return load_settings()


def reset_settings_cache() -> None:
    """
    Clear cached settings.

    Useful for tests.
    """
    get_settings.cache_clear()


def get_sanitized_settings_summary() -> dict[str, Any]:
    """
    Return a secret-safe config summary for startup logging.
    """
    settings = get_settings()
    return settings.sanitized_summary()


def get_sanitized_raw_config_dump() -> dict[str, Any]:
    """
    Return a sanitized dump of the full typed settings object.
    """
    settings = get_settings()
    return sanitize_config_payload(settings.model_dump())
