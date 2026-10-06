import json
from datetime import date, datetime, timezone
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, StrictInt
from app import seed
from app.db import connect, write_tx
from app.engines.fefo import consume_fefo, expire_lots
from app.modules.override_days import (
    OverrideError, alert_rows, lot_detail, pin_override,
)

app = FastAPI(title="Pantryfifo", version="0.1.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_OVERRIDE_STATUS = {
    "lot_not_found": 404,
    "not_on_shelf": 409,
    "override_days_non_positive": 400,
}

@app.on_event("startup")
def _startup(): seed.init_db()

@app.get("/api/health")
def health(): return {"ok": True, "project": "pantryfifo"}

@app.get("/api/items")
def items():
    c = connect(); rows = [dict(r) for r in c.execute("SELECT * FROM items")]; c.close(); return rows

@app.get("/api/fridge")
def fridge(layer: str | None = None):
    c = connect()
    q = """SELECT lots.*, items.name, items.layer, items.unit FROM lots
           JOIN items ON items.id=lots.item_id WHERE lots.status='on_shelf'"""
    args = []
    if layer:
        q += " AND items.layer=?"; args.append(layer)
    rows = [dict(r) for r in c.execute(q, args)]; c.close(); return rows

@app.get("/api/alerts")
def alerts():
    c = connect()
    try:
        return alert_rows(c)
    finally:
        c.close()

@app.get("/api/lots/{lot_id}")
def get_lot(lot_id: int):
    c = connect()
    try:
        d = lot_detail(c, lot_id)
        if d is None:
            raise HTTPException(404, "lot_not_found")
        return d
    finally:
        c.close()

class OverrideIn(BaseModel):
    override_days: StrictInt | None  # 正整数钉值；null 清除

@app.post("/api/lots/{lot_id}/override")
def set_override(lot_id: int, body: OverrideIn):
    c = connect()
    try:
        return pin_override(c, lot_id, body.override_days)
    except OverrideError as e:
        raise HTTPException(_OVERRIDE_STATUS.get(e.reason, 400), e.reason)
    finally:
        c.close()

class LotIn(BaseModel):
    item_id: int
    qty: float
    expiry: str

@app.post("/api/lots")
def inbound(body: LotIn):
    c = connect()
    item = c.execute("SELECT id FROM items WHERE id=?", (body.item_id,)).fetchone()
    if not item: c.close(); raise HTTPException(404, "item")
    cur = c.execute(
        "INSERT INTO lots(item_id,qty_in,qty_remain,expiry,status,data_quality) VALUES (?,?,?,?,?,?)",
        (body.item_id, body.qty, body.qty, body.expiry, "on_shelf", "clean"))
    c.commit(); lid = cur.lastrowid; c.close(); return {"id": lid}

class ConsumeIn(BaseModel):
    item_id: int
    qty: float
    note: str = ""

@app.post("/api/consume")
def consume(body: ConsumeIn):
    c = connect()
    try:
        with write_tx(c):
            lots = [dict(r) for r in c.execute(
                "SELECT * FROM lots WHERE item_id=? AND status='on_shelf' AND qty_remain>0", (body.item_id,))]
            result = consume_fefo(lots, body.qty)
            if not result["ok"] and result["reason"] == "qty_non_positive":
                raise HTTPException(400, result["reason"])
            if not result["ok"]:
                raise HTTPException(409, result)
            for d in result["deductions"]:
                c.execute("UPDATE lots SET qty_remain = qty_remain - ? WHERE id=?", (d["take"], d["lot_id"]))
                rem = c.execute("SELECT qty_remain FROM lots WHERE id=?", (d["lot_id"],)).fetchone()["qty_remain"]
                if rem <= 0:
                    c.execute("UPDATE lots SET status='consumed', qty_remain=0 WHERE id=?", (d["lot_id"],))
            c.execute("INSERT INTO consumptions(note,result_json,created_at) VALUES (?,?,?)",
                      (body.note, json.dumps(result), datetime.now(timezone.utc).isoformat()))
        return result
    finally:
        c.close()

@app.post("/api/expire-sweep")
def expire_sweep():
    c = connect()
    try:
        with write_tx(c):
            lots = [dict(r) for r in c.execute("SELECT * FROM lots WHERE status='on_shelf'")]
            ids = expire_lots(lots, date.today().isoformat())
            for i in ids:
                c.execute("UPDATE lots SET status='expired' WHERE id=?", (i,))
        return {"expired_ids": ids}
    finally:
        c.close()

@app.get("/api/settings")
def settings():
    c = connect(); rows = {r["key"]: r["value"] for r in c.execute("SELECT * FROM settings")}; c.close(); return rows

class SettingsIn(BaseModel):
    warn_days: StrictInt

@app.post("/api/settings")
def update_settings(body: SettingsIn):
    if body.warn_days < 0:
        raise HTTPException(400, "warn_days_negative")
    c = connect()
    try:
        with write_tx(c):
            c.execute(
                "INSERT INTO settings(key,value) VALUES ('warn_days',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(body.warn_days),))
    finally:
        c.close()
    return {"warn_days": str(body.warn_days)}
