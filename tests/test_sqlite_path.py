"""Tests for ``_resolve_sqlite_path`` in functions/sqlite.py."""
import sys
from types import SimpleNamespace

import pytest

sys.path.insert(0, ".")

# conftest.py stubs all HA modules before this runs
from custom_components.venice_ai.functions.sqlite import _resolve_sqlite_path


def _hass(config_dir):
    return SimpleNamespace(config=SimpleNamespace(config_dir=str(config_dir)))


def test_sqlite_url_inside_config_dir_allowed(tmp_path):
    db = tmp_path / "home-assistant_v2.db"
    db.touch()
    resolved = _resolve_sqlite_path(_hass(tmp_path), f"sqlite:///{db}")
    assert resolved == db.resolve()


def test_non_sqlite_scheme_rejected(tmp_path):
    # Postgres/MariaDB recorders used to fall through and produce a literal
    # file named "postgres://user@host/db" — fail fast with a clear message.
    with pytest.raises(ValueError, match="only supports sqlite"):
        _resolve_sqlite_path(_hass(tmp_path), "postgresql://user@host/db")


def test_mysql_scheme_rejected(tmp_path):
    with pytest.raises(ValueError, match="only supports sqlite"):
        _resolve_sqlite_path(_hass(tmp_path), "mysql://user@host/db")


def test_path_outside_config_dir_rejected(tmp_path):
    with pytest.raises(ValueError, match="outside the HA config directory"):
        _resolve_sqlite_path(_hass(tmp_path), "sqlite:////etc/passwd")


def test_path_traversal_sibling_rejected(tmp_path):
    # The path-component-boundary fix must apply here too — '/config_evil/x'
    # is not inside '/config'.
    sibling = tmp_path.parent / (tmp_path.name + "_evil")
    sibling.mkdir(exist_ok=True)
    with pytest.raises(ValueError, match="outside the HA config directory"):
        _resolve_sqlite_path(_hass(tmp_path), f"sqlite:///{sibling}/x.db")
