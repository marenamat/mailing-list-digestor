import os
from dataclasses import dataclass, field
import yaml

@dataclass
class Config:
    maildir_path: str = "/data/maildir"
    db_path: str = "/data/digestor.db"
    context_path: str = "/config/context.md"
    lists_path: str = "/config/lists.yaml"
    ollama_base_url: str = "http://ollama:11434"
    ollama_model: str = "gemma3:4b"
    anthropic_api_key: str = ""
    digest_time: str = "07:00"

    @classmethod
    def from_env(cls) -> "Config":
        return cls(
            maildir_path=os.environ.get("MAILDIR_PATH", "/data/maildir"),
            db_path=os.environ.get("DB_PATH", "/data/digestor.db"),
            context_path=os.environ.get("CONTEXT_PATH", "/config/context.md"),
            lists_path=os.environ.get("LISTS_PATH", "/config/lists.yaml"),
            ollama_base_url=os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434"),
            ollama_model=os.environ.get("OLLAMA_MODEL", "gemma3:4b"),
            anthropic_api_key=os.environ.get("ANTHROPIC_API_KEY", ""),
            digest_time=os.environ.get("DIGEST_TIME", "07:00"),
        )

    def load_context(self) -> str:
        try:
            with open(self.context_path) as f:
                return f.read()
        except FileNotFoundError:
            return ""

    def load_lists(self) -> dict[str, list[str]]:
        try:
            with open(self.lists_path) as f:
                data = yaml.safe_load(f)
            if not isinstance(data, dict):
                return {}
            return data.get("working_groups", {})
        except (FileNotFoundError, yaml.YAMLError):
            return {}
