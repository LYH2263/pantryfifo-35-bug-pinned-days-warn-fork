import os, sqlite3, threading
from contextlib import contextmanager
from pathlib import Path

def db_path() -> Path:
    d = Path(os.environ.get("DATA_DIR", Path(__file__).resolve().parent.parent / "data"))
    d.mkdir(parents=True, exist_ok=True)
    return d / "pantryfifo.db"

def connect():
    c = sqlite3.connect(db_path(), timeout=30)
    c.row_factory = sqlite3.Row
    return c

# 单进程多线程（uvicorn 线程池）下的写互斥：钉值写入 / 改 warn_days /
# 过期下架 / 消费并发时串行落库，避免 sqlite 单写锁下的等待饥饿。
_write_lock = threading.Lock()

@contextmanager
def write_tx(conn):
    """进程内写互斥 + BEGIN IMMEDIATE；异常回滚，提交后释放。"""
    with _write_lock:
        conn.execute("BEGIN IMMEDIATE")
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
