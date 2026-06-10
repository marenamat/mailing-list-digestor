import os, textwrap, pytest
from pathlib import Path
from digestor.config import Config

def test_from_env_defaults(monkeypatch, tmp_path):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    monkeypatch.delenv("OLLAMA_MODEL", raising=False)
    cfg = Config.from_env()
    assert cfg.maildir_path == "/data/maildir"
    assert cfg.db_path == "/data/digestor.db"
    assert cfg.ollama_model == "gemma3:4b"
    assert cfg.digest_time == "07:00"

def test_from_env_overrides(monkeypatch):
    monkeypatch.setenv("MAILDIR_PATH", "/tmp/md")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "sk-test")
    monkeypatch.setenv("OLLAMA_MODEL", "llama3.2:3b")
    cfg = Config.from_env()
    assert cfg.maildir_path == "/tmp/md"
    assert cfg.anthropic_api_key == "sk-test"
    assert cfg.ollama_model == "llama3.2:3b"

def test_load_context(tmp_path):
    ctx_file = tmp_path / "context.md"
    ctx_file.write_text("I care about QUIC.")
    cfg = Config.from_env()
    cfg.context_path = str(ctx_file)
    assert cfg.load_context() == "I care about QUIC."

def test_load_context_missing(tmp_path):
    cfg = Config.from_env()
    cfg.context_path = str(tmp_path / "missing.md")
    assert cfg.load_context() == ""

def test_load_lists(tmp_path):
    lists_file = tmp_path / "lists.yaml"
    lists_file.write_text(textwrap.dedent("""\
        working_groups:
          QUIC:
            - quic@ietf.org
          TLS:
            - tls@ietf.org
    """))
    cfg = Config.from_env()
    cfg.lists_path = str(lists_file)
    lists = cfg.load_lists()
    assert lists == {"QUIC": ["quic@ietf.org"], "TLS": ["tls@ietf.org"]}

def test_load_lists_missing(tmp_path):
    cfg = Config.from_env()
    cfg.lists_path = str(tmp_path / "missing.yaml")
    assert cfg.load_lists() == {}
