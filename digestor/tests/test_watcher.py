import time, shutil
from pathlib import Path
import pytest
from watchdog.events import FileCreatedEvent
from digestor.watcher import start_watcher, _NewMailHandler

def test_watcher_fires_on_new_file(tmp_path):
    maildir = tmp_path / "maildir"
    (maildir / "new").mkdir(parents=True)
    (maildir / "cur").mkdir()
    (maildir / "tmp").mkdir()

    seen = []
    handler = _NewMailHandler(str(maildir), lambda p: seen.append(p))

    eml = maildir / "new" / "test.eml"
    eml.write_text("Subject: Test\r\n\r\nBody")

    # Manually trigger the event (watchdog may not work in test env)
    event = FileCreatedEvent(str(eml))
    handler.on_created(event)

    assert len(seen) == 1
    assert seen[0] == eml

def test_watcher_ignores_non_new_dir(tmp_path):
    maildir = tmp_path / "maildir"
    (maildir / "new").mkdir(parents=True)
    (maildir / "cur").mkdir()
    (maildir / "tmp").mkdir()

    seen = []
    handler = _NewMailHandler(str(maildir), lambda p: seen.append(p))

    old_file = maildir / "cur" / "old.eml"
    old_file.write_text("old mail")

    # Manually trigger the event
    event = FileCreatedEvent(str(old_file))
    handler.on_created(event)

    assert len(seen) == 0
