import logging
from pathlib import Path
from typing import Callable
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileCreatedEvent

log = logging.getLogger(__name__)

__all__ = ["start_watcher", "_NewMailHandler"]


class _NewMailHandler(FileSystemEventHandler):
    def __init__(self, new_dir: str, callback: Callable[[Path], None]):
        self._new_dir = str(Path(new_dir) / "new")
        self._callback = callback

    def on_created(self, event: FileCreatedEvent) -> None:
        if event.is_directory:
            return
        path = Path(event.src_path)
        if str(path.parent) == self._new_dir:
            log.info("New message: %s", path)
            try:
                self._callback(path)
            except Exception:
                log.exception("Error processing %s", path)


def start_watcher(maildir: str, callback: Callable[[Path], None]) -> Observer:
    observer = Observer()
    observer.schedule(_NewMailHandler(maildir, callback), maildir, recursive=False)
    observer.start()
    return observer
