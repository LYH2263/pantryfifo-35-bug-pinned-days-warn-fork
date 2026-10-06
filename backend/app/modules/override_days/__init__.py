"""手钉可放天数：在架批可写入 override_days，全系统共用一条紧急/资格规则。

规则唯一来源（本模块），顶条、批次详情、过期下架、FEFO 全部由此派生：
  - 生效到期日 = override_set_at + override_days（无钉则为入库 expiry）。
  - 顶条紧急吃写入值；全层主行仍显示入库到期日（lots.expiry 永不改写）。
  - 日历已过期批允许钉：钉后下架名单 / 顶条 expired / 在架资格同看生效到期日。
  - warn_days 每次求值时从 settings 现读，不缓存；钉值写入 / 改 warn_days /
    过期下架各自经 write_tx（进程内写互斥 + BEGIN IMMEDIATE）串行化，
    交错后各视图仍从同一批已提交列重算。
"""
from datetime import date, timedelta

from app.db import write_tx

DEFAULT_WARN_DAYS = 3


class OverrideError(ValueError):
    """reason: lot_not_found / not_on_shelf / override_days_non_positive"""

    def __init__(self, reason):
        super().__init__(reason)
        self.reason = reason


def validate_override_days(days) -> int:
    """钉值必须为正整数；非正数（及非整数）拒写。"""
    if isinstance(days, bool) or not isinstance(days, int) or days <= 0:
        raise OverrideError("override_days_non_positive")
    return days


def effective_expiry(lot: dict) -> str | None:
    """生效到期日：钉了则 写入日 + override_days，否则入库 expiry。"""
    days = lot.get("override_days")
    set_at = lot.get("override_set_at")
    if days is None or not set_at:
        return lot.get("expiry")
    return (date.fromisoformat(set_at) + timedelta(days=int(days))).isoformat()


def lot_level(lot: dict, warn_days: int, today: date | None = None) -> dict:
    """单批紧急结论：expired / soon / ok + days_left + effective_expiry。"""
    today = today or date.today()
    eff = effective_expiry(lot)
    if not eff:
        return {"level": "ok", "days_left": None, "effective_expiry": None}
    days_left = (date.fromisoformat(eff) - today).days
    if days_left < 0:
        level = "expired"
    elif days_left <= warn_days:
        level = "soon"
    else:
        level = "ok"
    return {"level": level, "days_left": days_left, "effective_expiry": eff}


def warn_days(conn) -> int:
    """当前预警阈值：每次求值现读 settings，不缓存。"""
    row = conn.execute("SELECT value FROM settings WHERE key='warn_days'").fetchone()
    return int(row["value"]) if row else DEFAULT_WARN_DAYS


_LOT_SQL = """SELECT lots.*, items.name, items.layer, items.unit FROM lots
              JOIN items ON items.id=lots.item_id"""


def lot_detail(conn, lot_id: int, today: date | None = None) -> dict | None:
    """批次详情：原始列 + 当前 warn_days 下的紧急结论（与顶条同一规则）。"""
    row = conn.execute(_LOT_SQL + " WHERE lots.id=?", (lot_id,)).fetchone()
    if not row:
        return None
    warn = warn_days(conn)
    d = dict(row)
    d.update(lot_level(d, warn, today))
    d["warn_days"] = warn
    return d


def alert_rows(conn, today: date | None = None) -> list[dict]:
    """顶条数据：在架有余量且生效到期日已过期或临期，最急的在前。

    与详情、过期下架同一生效到期日口径：已钉批吃钉值，不剥 pin。
    """
    rows = [dict(r) for r in conn.execute(
        _LOT_SQL + " WHERE lots.status='on_shelf' AND lots.qty_remain>0")]
    warn = warn_days(conn)
    out = []
    for r in rows:
        lv = lot_level(r, warn, today)
        if lv["level"] in ("expired", "soon"):
            r.update(lv)
            out.append(r)
    out.sort(key=lambda r: (r["effective_expiry"], r["id"]))
    return out


def pin_override(conn, lot_id: int, days, today: date | None = None) -> dict:
    """在架批写入钉值（days=None 清除）。write_tx 与并发写串行化。

    拒写（OverrideError）时不落任何改动，各入口停在改前。
    返回写入后的批次详情（与顶条同一规则算出的结论）。
    """
    today = today or date.today()
    with write_tx(conn):
        row = conn.execute("SELECT * FROM lots WHERE id=?", (lot_id,)).fetchone()
        if not row:
            raise OverrideError("lot_not_found")
        if row["status"] != "on_shelf":
            raise OverrideError("not_on_shelf")
        if days is None:
            conn.execute(
                "UPDATE lots SET override_days=NULL, override_set_at=NULL WHERE id=?",
                (lot_id,))
        else:
            conn.execute(
                "UPDATE lots SET override_days=?, override_set_at=? WHERE id=?",
                (validate_override_days(days), today.isoformat(), lot_id))
    return lot_detail(conn, lot_id, today)
