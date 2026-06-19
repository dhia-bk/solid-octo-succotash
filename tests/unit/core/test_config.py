from pathlib import Path

import pytest

from app.core import config as config_module
from app.core.exceptions import ConfigurationError, InvalidConfigError


def _write_yaml(path: Path, payload: str) -> None:
    path.write_text(payload.strip() + "\n", encoding="utf-8")


def _write_minimal_config_set(config_dir: Path) -> None:
    _write_yaml(
        config_dir / "base.yaml",
        """
app:
  name: project-pulse-kg
  env: dev
runtime:
  default_batch_size: 100
  max_batch_size: 1000
checkpoints:
  namespace: project_pulse
mysql:
  host: localhost
  db: pulse
  user: pulse_user
  password: pulse_password
neo4j:
  uri: bolt://localhost:7687
  user: neo4j
  password: neo4j_password
  database: neo4j
metadata_db:
  host: localhost
  name: metadata
  user: meta_user
  password: meta_password
""",
    )
    _write_yaml(config_dir / "dev.yaml", "app:\n  env: dev\n")
    _write_yaml(config_dir / "staging.yaml", "app:\n  env: staging\n")
    _write_yaml(config_dir / "prod.yaml", "app:\n  env: prod\n")
    _write_yaml(config_dir / "logging.yaml", "{}")
    _write_yaml(config_dir / "ontology.yaml", "{}")
    _write_yaml(config_dir / "weighting.yaml", "{}")
    _write_yaml(config_dir / "inference.yaml", "{}")
    _write_yaml(config_dir / "gds.yaml", "{}")
    _write_yaml(config_dir / "source_inclusion.yaml", "{}")
    _write_yaml(config_dir / "serving.yaml", "{}")


def test_load_settings_succeeds_with_minimal_valid_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_minimal_config_set(tmp_path)

    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("APP_ENV", "dev")
    config_module.reset_settings_cache()

    settings = config_module.load_settings()

    assert settings.app.env == "dev"
    assert settings.mysql.host == "localhost"
    assert settings.neo4j.database == "neo4j"
    assert settings.metadata_db.name == "metadata"


def test_load_settings_applies_environment_overrides(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_minimal_config_set(tmp_path)

    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("APP_ENV", "dev")
    monkeypatch.setenv("MYSQL_HOST", "override-host")
    monkeypatch.setenv("APP_NAME", "override-name")
    config_module.reset_settings_cache()

    settings = config_module.load_settings()

    assert settings.mysql.host == "override-host"
    assert settings.app.name == "override-name"


def test_load_settings_fails_for_missing_required_mysql_fields(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_minimal_config_set(tmp_path)
    _write_yaml(
        tmp_path / "base.yaml",
        """
app:
  name: project-pulse-kg
  env: dev
neo4j:
  uri: bolt://localhost:7687
  user: neo4j
  password: neo4j_password
  database: neo4j
metadata_db:
  host: localhost
  name: metadata
  user: meta_user
  password: meta_password
""",
    )

    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("APP_ENV", "dev")
    config_module.reset_settings_cache()

    with pytest.raises(InvalidConfigError):
        config_module.load_settings()


def test_resolve_config_dir_raises_for_missing_directory(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("CONFIG_DIR", str(Path("does-not-exist-config-dir").resolve()))

    with pytest.raises(ConfigurationError):
        config_module._resolve_config_dir()


def test_get_sanitized_raw_config_dump_masks_secrets(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _write_minimal_config_set(tmp_path)

    monkeypatch.setenv("CONFIG_DIR", str(tmp_path))
    monkeypatch.setenv("APP_ENV", "dev")
    config_module.reset_settings_cache()

    dumped = config_module.get_sanitized_raw_config_dump()

    assert dumped["mysql"]["password"] != "pulse_password"
    assert dumped["neo4j"]["password"] != "neo4j_password"
    assert dumped["metadata_db"]["password"] != "meta_password"
