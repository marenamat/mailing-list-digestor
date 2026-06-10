import os
from dataclasses import dataclass, field


@dataclass
class Config:
    homeserver: str = ""
    username: str = ""
    password: str = ""
    whitelist: set[str] = field(default_factory=set)
    db_path: str = "/data/digestor.db"
    room_id: str = ""
    poll_interval_s: int = 30

    @classmethod
    def from_env(cls) -> "Config":
        whitelist_raw = os.environ.get("MATRIX_WHITELIST", "")
        whitelist = {u.strip() for u in whitelist_raw.split(",") if u.strip()}
        return cls(
            homeserver=os.environ.get("MATRIX_HOMESERVER", ""),
            username=os.environ.get("MATRIX_USERNAME", ""),
            password=os.environ.get("MATRIX_PASSWORD", ""),
            whitelist=whitelist,
            db_path=os.environ.get("DB_PATH", "/data/digestor.db"),
            room_id=os.environ.get("MATRIX_ROOM_ID", ""),
            poll_interval_s=int(os.environ.get("POLL_INTERVAL_S", "30")),
        )
