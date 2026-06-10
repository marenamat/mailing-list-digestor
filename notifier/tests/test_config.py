import os, pytest
from notifier.config import Config

def test_from_env_defaults(monkeypatch):
    for k in ("MATRIX_HOMESERVER", "MATRIX_USERNAME", "MATRIX_PASSWORD",
              "MATRIX_WHITELIST", "DB_PATH"):
        monkeypatch.delenv(k, raising=False)
    cfg = Config.from_env()
    assert cfg.db_path == "/data/digestor.db"
    assert cfg.poll_interval_s == 30

def test_from_env_overrides(monkeypatch):
    monkeypatch.setenv("MATRIX_HOMESERVER", "https://matrix.example.com")
    monkeypatch.setenv("MATRIX_USERNAME", "@bot:example.com")
    monkeypatch.setenv("MATRIX_PASSWORD", "secret")
    monkeypatch.setenv("MATRIX_WHITELIST", "@alice:example.com")
    monkeypatch.setenv("DB_PATH", "/tmp/db.sqlite")
    cfg = Config.from_env()
    assert cfg.homeserver == "https://matrix.example.com"
    assert cfg.username == "@bot:example.com"
    assert cfg.password == "secret"
    assert cfg.whitelist == {"@alice:example.com"}
    assert cfg.db_path == "/tmp/db.sqlite"

def test_whitelist_multiple(monkeypatch):
    monkeypatch.setenv("MATRIX_WHITELIST", "@alice:example.com,@bob:example.com")
    cfg = Config.from_env()
    assert "@alice:example.com" in cfg.whitelist
    assert "@bob:example.com" in cfg.whitelist
