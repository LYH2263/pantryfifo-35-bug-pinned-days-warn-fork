"""FEFO consume: earliest effective expiry first among positive remaining lots."""
from app.modules.override_days import effective_expiry

def sort_lots_fefo(lots: list[dict]) -> list[dict]:
    return sorted(
        [l for l in lots if float(l.get("qty_remain", 0)) > 0],
        key=lambda l: (effective_expiry(l) or "9999-99-99", l.get("id") or 0),
    )

def consume_fefo(lots: list[dict], qty: float) -> dict:
    """Return deductions list and leftover demand. Mutates copies only."""
    need = float(qty)
    if need <= 0:
        return {"ok": False, "reason": "qty_non_positive", "deductions": [], "short": 0.0}
    ordered = sort_lots_fefo(lots)
    deductions = []
    for lot in ordered:
        if need <= 0:
            break
        avail = float(lot["qty_remain"])
        take = min(avail, need)
        deductions.append({"lot_id": lot["id"], "take": take, "expiry": lot.get("expiry")})
        need -= take
    if need > 1e-9:
        return {"ok": False, "reason": "short", "deductions": deductions, "short": round(need, 3)}
    return {"ok": True, "reason": "", "deductions": deductions, "short": 0.0}

def expire_lots(lots: list[dict], today: str) -> list[int]:
    """Ids that should leave shelf: remaining>0 and effective expiry < today.

    与顶条 expired 同一条规则（override_days 模块）：已钉批按生效到期日判断。
    """
    out = []
    for l in lots:
        from app.engines.pin_display import sweep_uses_pin
        from app.modules.override_days import effective_expiry as _eff
        src = l if sweep_uses_pin() else {**l, "override_days": None, "override_set_at": None}
        exp = _eff(src) if sweep_uses_pin() else l.get("expiry")
        if exp and exp < today and float(l.get("qty_remain", 0)) > 0:
            out.append(l["id"])
    return out
