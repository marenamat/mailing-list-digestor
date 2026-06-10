import time
from pathlib import Path
import pytest
from digestor.watcher import start_watcher


def test_watcher_fires_on_new_file(tmp_path):
    maildir = tmp_path / "maildir"
    (maildir / "new").mkdir(parents=True)
    (maildir / "cur").mkdir()
    (maildir / "tmp").mkdir()

    seen = []
    observer = start_watcher(str(maildir), lambda p: seen.append(p))

    try:
        eml = maildir / "new" / "test.eml"
        eml.write_text("Subject: Test\r\n\r\nBody")
        # give watchdog time to fire
        for _ in range(50):
            if seen:
                break
            time.sleep(0.1)
        assert len(seen) == 1
        assert seen[0] == eml
    finally:
        observer.stop()
        observer.join()


def test_watcher_ignores_non_new_dir(tmp_path):
    maildir = tmp_path / "maildir"
    (maildir / "new").mkdir(parents=True)
    (maildir / "cur").mkdir()
    (maildir / "tmp").mkdir()

    seen = []
    observer = start_watcher(str(maildir), lambda p: seen.append(p))

    try:
        (maildir / "cur" / "old.eml").write_text("old mail")
        time.sleep(0.5)
        assert len(seen) == 0
    finally:
        observer.stop()
        observer.join()
