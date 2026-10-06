"""钉值一致性：详情 / 紧急条 / 收走（过期下架）/ FEFO 对同一批同一结论。

固定 today 不可控，用 date.today() 动态造入库到期日，钉后天数是绝对差值。
"""
from datetime import date, timedelta

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    from app.main import app
    with TestClient(app) as c:
        yield c


def _inbound(client, item_id, expiry, qty=2):
    r = client.post("/api/lots", json={"item_id": item_id, "qty": qty, "expiry": expiry})
    assert r.status_code == 200, r.text
    return r.json()["id"]


def _alert_map(client):
    return {a["id"]: a for a in client.get("/api/alerts").json()}


def _fridge_map(client):
    return {x["id"]: x for x in client.get("/api/fridge").json()}


def test_unpinned_expired_is_expired_everywhere(client):
    today = date.today()
    lid = _inbound(client, 1, (today - timedelta(days=5)).isoformat())

    detail = client.get(f"/api/lots/{lid}").json()
    assert detail["level"] == "expired"
    assert detail["days_left"] == -5
    assert _alert_map(client)[lid]["level"] == "expired"

    swept = client.post("/api/expire-sweep").json()["expired_ids"]
    assert lid in swept


def test_pin_aligns_detail_alerts_sweep_and_badge(client):
    today = date.today()
    expiry = (today - timedelta(days=5)).isoformat()
    lid = _inbound(client, 1, expiry)

    r = client.post(f"/api/lots/{lid}/override", json={"override_days": 30})
    assert r.status_code == 200, r.text
    pinned = r.json()
    assert pinned["level"] == "ok"
    assert pinned["days_left"] == 30
    assert pinned["effective_expiry"] == (today + timedelta(days=30)).isoformat()
    # 主行入库到期日永不被钉值改写
    assert pinned["expiry"] == expiry

    # 紧急条不再按入库日历标过期
    assert lid not in _alert_map(client)

    # 收走按同一生效到期日：入库已过期但钉到未来 -> 不被收走
    swept = client.post("/api/expire-sweep").json()["expired_ids"]
    assert lid not in swept

    # 分层角标与详情同一结论（主行日期仍是入库日期）
    f = _fridge_map(client)[lid]
    assert f["expiry"] == expiry
    assert f["level"] == "ok"
    assert f["days_left"] == 30
    assert f["override_days"] == 30

    # 重新取详情仍一致
    detail = client.get(f"/api/lots/{lid}").json()
    assert detail["level"] == "ok" and detail["days_left"] == 30


def test_changing_warn_days_never_rewrites_pin(client):
    today = date.today()
    lid = _inbound(client, 1, (today - timedelta(days=5)).isoformat())
    client.post(f"/api/lots/{lid}/override", json={"override_days": 30})
    before = client.get(f"/api/lots/{lid}").json()

    r = client.post("/api/settings", json={"warn_days": 40})
    assert r.status_code == 200, r.text

    after = client.get(f"/api/lots/{lid}").json()
    # 钉住的值与生效到期日不被预警天数改写
    assert after["override_days"] == 30
    assert after["override_set_at"] == before["override_set_at"]
    assert after["effective_expiry"] == before["effective_expiry"]
    assert after["days_left"] == 30
    # 只改紧急归类：30 <= 40 -> soon（详情与紧急条一致）
    assert after["level"] == "soon"
    assert _alert_map(client)[lid]["level"] == "soon"
    # 收走资格仍只看生效到期日，不被 warn_days 带走
    assert lid not in client.post("/api/expire-sweep").json()["expired_ids"]


def test_invalid_pin_rejected_everywhere_stays_at_before(client):
    today = date.today()
    lid = _inbound(client, 1, (today - timedelta(days=5)).isoformat())
    client.post(f"/api/lots/{lid}/override", json={"override_days": 30})
    client.post("/api/settings", json={"warn_days": 40})

    for bad in (0, -3):
        r = client.post(f"/api/lots/{lid}/override", json={"override_days": bad})
        assert r.status_code == 400, r.text

    detail = client.get(f"/api/lots/{lid}").json()
    assert detail["override_days"] == 30
    assert detail["level"] == "soon" and detail["days_left"] == 30
    assert _alert_map(client)[lid]["days_left"] == 30
    assert lid not in client.post("/api/expire-sweep").json()["expired_ids"]


def test_calendar_expired_lot_allowed_to_pin_and_regains_eligibility(client):
    """已过期批：允许改钉；钉后详情/紧急条/收走同一世界（留下），清除后同走。"""
    today = date.today()
    lid = _inbound(client, 1, (today - timedelta(days=5)).isoformat())
    assert _alert_map(client)[lid]["level"] == "expired"

    r = client.post(f"/api/lots/{lid}/override", json={"override_days": 10})
    assert r.status_code == 200, r.text
    assert r.json()["level"] == "ok"
    assert lid not in _alert_map(client)
    assert lid not in client.post("/api/expire-sweep").json()["expired_ids"]

    client.post(f"/api/lots/{lid}/override", json={"override_days": None})
    detail = client.get(f"/api/lots/{lid}").json()
    assert detail["override_days"] is None
    assert detail["level"] == "expired"
    assert lid in client.post("/api/expire-sweep").json()["expired_ids"]


def test_fefo_uses_effective_expiry_after_pin(client):
    # 用独立新品类，避开种子数据里更早的在架批
    from app.db import connect
    c = connect()
    cur = c.execute("INSERT INTO items(name,layer,unit) VALUES ('测试品','mid','个')")
    item_id = cur.lastrowid
    c.commit(); c.close()

    today = date.today()
    near = _inbound(client, item_id, (today + timedelta(days=1)).isoformat(), qty=1)   # 未钉，明天到期
    pinned_expired = _inbound(client, item_id, (today - timedelta(days=5)).isoformat(), qty=1)
    client.post(f"/api/lots/{pinned_expired}/override", json={"override_days": 30})

    r = client.post("/api/consume", json={"item_id": item_id, "qty": 1})
    assert r.status_code == 200, r.text
    first = r.json()["deductions"][0]
    # 入库更早但被钉到 30 天后的批排后；先扣未钉的明天到期批
    assert first["lot_id"] == near
