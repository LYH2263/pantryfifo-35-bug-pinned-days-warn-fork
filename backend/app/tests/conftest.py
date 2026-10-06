import pytest
from fastapi.testclient import TestClient

from app import seed


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """每用例一座空库：DATA_DIR 指到临时目录后重建 schema + 种子。"""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    seed.init_db()
    from app.main import app
    with TestClient(app) as c:
        yield c
