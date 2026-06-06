"""Tests for config load/save."""

import json
import os
import stat

import poe2price.config as config_mod
from poe2price.config import Config


def _point_config_at(tmp_path, monkeypatch):
    """Redirect the module's config path into a temp dir."""
    cfg_dir = tmp_path / "poe2-pricecheck"
    cfg_path = cfg_dir / "config.json"
    monkeypatch.setattr(config_mod, "CONFIG_DIR", str(cfg_dir))
    monkeypatch.setattr(config_mod, "CONFIG_PATH", str(cfg_path))
    return cfg_path


def test_defaults():
    cfg = Config()
    assert cfg.league == "Runes of Aldur"
    assert cfg.hotkey == "<ctrl>+d"
    assert cfg.poesessid == ""
    assert cfg.max_listings == 10


def test_load_creates_default_file(tmp_path, monkeypatch):
    cfg_path = _point_config_at(tmp_path, monkeypatch)
    assert not cfg_path.exists()
    cfg = Config.load()
    assert cfg_path.exists()
    assert cfg.league == "Runes of Aldur"


def test_save_is_chmod_600(tmp_path, monkeypatch):
    cfg_path = _point_config_at(tmp_path, monkeypatch)
    Config(poesessid="secret").save()
    mode = stat.S_IMODE(os.stat(cfg_path).st_mode)
    assert mode == 0o600  # POESESSID is a secret


def test_round_trip_preserves_values(tmp_path, monkeypatch):
    _point_config_at(tmp_path, monkeypatch)
    Config(league="Standard", poesessid="abc123", max_listings=5).save()
    loaded = Config.load()
    assert loaded.league == "Standard"
    assert loaded.poesessid == "abc123"
    assert loaded.max_listings == 5


def test_load_ignores_unknown_keys(tmp_path, monkeypatch):
    cfg_path = _point_config_at(tmp_path, monkeypatch)
    cfg_path.parent.mkdir(parents=True)
    cfg_path.write_text(json.dumps({"league": "Standard", "bogus_key": 1}))
    loaded = Config.load()  # must not raise on the unknown field
    assert loaded.league == "Standard"
    assert not hasattr(loaded, "bogus_key")
