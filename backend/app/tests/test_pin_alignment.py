"""钉值对齐验收：详情钉值、顶条紧急、过期收走对已钉批必须同一结论。

覆盖：
  - 日历已过期批允许钉，钉后顶条 / 收走 / 在架资格同看生效到期日；
  - 顶条紧急按钉值算，不按入库日历 + 新 warn_days 变基；
  - 改 warn_days 不改写已钉列（override_days / override_set_at）；
  - 非法钉值拒写后详情、顶条、收走停在改前；
  - 已下架批拒钉（not_on_shelf），与收走同一世界；
  - 总表主行仍是入库到期日，lots.expiry 永不改写。
"""
from datetime import date, timedelta


def _expiry(days_from_today: int) -> str:
    return (date.today() + timedelta(days=days_from_today)).isoformat()


def _add_lot(client, days_from_today: int, qty: float = 5) -> int:
    r = client.post("/api/lots", json={"item_id": 1, "qty": qty, "expiry": _expiry(days_from_today)})
    assert r.status_code == 200
    return r.json()["id"]


def _detail(client, lot_id: int) -> dict:
    r = client.get(f"/api/lots/{lot_id}")
    assert r.status_code == 200
    return r.json()


def _alerts(client) -> list[dict]:
    return client.get("/api/alerts").json()


def _alert_for(client, lot_id: int) -> dict | None:
    return next((a for a in _alerts(client) if a["id"] == lot_id), None)


def _pin(client, lot_id: int, days):
    return client.post(f"/api/lots/{lot_id}/override", json={"override_days": days})


def _sweep(client) -> list[int]:
    return client.post("/api/expire-sweep").json()["expired_ids"]


def test_expired_lot_pin_unifies_detail_alert_and_sweep(client):
    """日历已过期批钉 5 天：详情 ok、顶条不再 expired、收走不再带走。"""
    lot_id = _add_lot(client, -1)
    assert _detail(client, lot_id)["level"] == "expired"
    assert _alert_for(client, lot_id)["level"] == "expired"

    r = _pin(client, lot_id, 5)
    assert r.status_code == 200

    d = _detail(client, lot_id)
    assert (d["override_days"], d["override_set_at"]) == (5, date.today().isoformat())
    assert (d["level"], d["days_left"]) == ("ok", 5)
    assert d["effective_expiry"] == _expiry(5)

    # 顶条与详情同一结论：不再按入库日历把它标紧急
    assert _alert_for(client, lot_id) is None
    # 收走与详情同一世界：不再按旧日历带走
    assert lot_id not in _sweep(client)
    assert _detail(client, lot_id)["status"] == "on_shelf"

    # 总表主行仍是入库到期日，原始列不被钉改写
    row = next(x for x in client.get("/api/fridge").json() if x["id"] == lot_id)
    assert row["expiry"] == _expiry(-1)
    assert row["override_days"] == 5


def test_alert_urgency_follows_pin_not_calendar(client):
    """日历临期但钉远了 → 顶条放行；日历很远但钉近了 → 顶条标紧急。"""
    calm = _add_lot(client, 1)    # 入库日历明天到期，默认 warn_days=3 下本临期
    urgent = _add_lot(client, 30)  # 入库日历还有 30 天，本不临期

    assert _pin(client, calm, 30).status_code == 200
    assert _pin(client, urgent, 1).status_code == 200

    assert _alert_for(client, calm) is None
    a = _alert_for(client, urgent)
    assert a is not None and a["level"] == "soon" and a["days_left"] == 1

    # 顶条行与详情同一结论
    d = _detail(client, urgent)
    assert (a["days_left"], a["effective_expiry"], a["level"]) == (
        d["days_left"], d["effective_expiry"], d["level"])
    # 钉远的批收走也不动它
    assert calm not in _sweep(client) and urgent not in _sweep(client)


def test_warn_days_change_does_not_rewrite_pin(client):
    """改预警天数只改结论，不改写已钉的 override_days / override_set_at。"""
    lot_id = _add_lot(client, 10)
    assert _pin(client, lot_id, 4).status_code == 200
    before = _detail(client, lot_id)
    assert before["level"] == "ok"  # 4 > 默认 warn_days=3

    assert client.post("/api/settings", json={"warn_days": 10}).status_code == 200
    d = _detail(client, lot_id)
    assert (d["override_days"], d["override_set_at"]) == (4, before["override_set_at"])
    assert (d["level"], d["days_left"]) == ("soon", 4)  # 结论按新阈值现算
    assert _alert_for(client, lot_id)["days_left"] == 4  # 顶条同一结论

    assert client.post("/api/settings", json={"warn_days": 3}).status_code == 200
    d = _detail(client, lot_id)
    assert (d["override_days"], d["level"]) == (4, "ok")
    assert _alert_for(client, lot_id) is None


def test_illegal_pin_rejected_and_views_stay_unchanged(client):
    """非法钉值拒写：详情、顶条、收走全部停在改前。"""
    lot_id = _add_lot(client, -1)
    assert _pin(client, lot_id, 5).status_code == 200
    detail_before = _detail(client, lot_id)
    alerts_before = _alerts(client)

    for bad in (0, -2, 1.5, "abc", True):
        assert _pin(client, lot_id, bad).status_code in (400, 422), bad

    assert _detail(client, lot_id) == detail_before
    assert _alerts(client) == alerts_before
    assert lot_id not in _sweep(client)  # 收走仍认改前的钉
    assert _detail(client, lot_id)["status"] == "on_shelf"


def test_swept_lot_refuses_pin(client):
    """已收走的批：详情与收走同一世界，钉写入被拒。"""
    lot_id = _add_lot(client, -1)
    assert lot_id in _sweep(client)
    assert _detail(client, lot_id)["status"] == "expired"

    r = _pin(client, lot_id, 5)
    assert r.status_code == 409 and r.json()["detail"] == "not_on_shelf"
    d = _detail(client, lot_id)
    assert d["override_days"] is None and d["level"] == "expired"


def test_clear_pin_restores_calendar_for_all_views(client):
    """清钉后详情、顶条、收走一起回到入库日历。"""
    lot_id = _add_lot(client, -1)
    assert _pin(client, lot_id, 5).status_code == 200
    assert _alert_for(client, lot_id) is None

    assert _pin(client, lot_id, None).status_code == 200
    d = _detail(client, lot_id)
    assert d["override_days"] is None and d["level"] == "expired"
    assert _alert_for(client, lot_id)["level"] == "expired"
    assert lot_id in _sweep(client)
