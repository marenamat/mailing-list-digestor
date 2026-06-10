import time, threading, urllib.request, json
import pytest
from digestor.db import init_db
from digestor.health import start_health_server

def test_healthz_returns_200(tmp_path):
    db_path = str(tmp_path / "test.db")
    init_db(db_path)
    t = start_health_server(db_path, port=18080)
    time.sleep(0.2)
    resp = urllib.request.urlopen("http://127.0.0.1:18080/healthz", timeout=3)
    assert resp.status == 200
    body = json.loads(resp.read())
    assert body["status"] == "ok"
    assert "db" in body
