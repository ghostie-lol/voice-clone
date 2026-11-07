"""Usage metering, free allowance and one-time lifetime keys (SQLite)."""
import hashlib
import os
import re
import secrets
import sqlite3
import sys
import threading
import time
from pathlib import Path

import psutil

DATA = Path(os.getenv("DATA_DIR", "data"))
DATA.mkdir(parents=True, exist_ok=True)
DB_PATH = DATA / "app.db"

# Free "compute units" per device per calendar month. 1 unit = 1 second of
# generation time on this server. Tune these with environment variables.
FREE_UNITS = float(os.getenv("FREE_UNITS_PER_MONTH", "300"))
HEAVY_RAM_GB = float(os.getenv("HEAVY_RAM_GB", "6"))
HEAVY_CPU_SECONDS = float(os.getenv("HEAVY_CPU_SECONDS", "60"))
HEAVY_MULTIPLIER = float(os.getenv("HEAVY_MULTIPLIER", "3"))

_lock = threading.Lock()
DEVICE_RE = re.compile(r"^[A-Za-z0-9-]{8,64}$")


def _db():
    c = sqlite3.connect(DB_PATH)
    c.row_factory = sqlite3.Row
    return c


def init():
    with _db() as c:
        c.executescript(
            """
            CREATE TABLE IF NOT EXISTS devices(
              id TEXT PRIMARY KEY, created REAL, unlimited INTEGER DEFAULT 0);
            CREATE TABLE IF NOT EXISTS keys(
              hash TEXT PRIMARY KEY, created REAL, redeemed_by TEXT, redeemed_at REAL);
            CREATE TABLE IF NOT EXISTS usage(
              id INTEGER PRIMARY KEY AUTOINCREMENT, device TEXT, ts REAL,
              wall REAL, cpu REAL, peak_gb REAL, units REAL, heavy INTEGER);
            """
        )


init()


def _month_start() -> float:
    t = time.gmtime()
    return time.mktime((t.tm_year, t.tm_mon, 1, 0, 0, 0, 0, 0, 0)) - time.timezone


def ensure_device(device: str):
    with _lock, _db() as c:
        c.execute(
            "INSERT OR IGNORE INTO devices(id, created) VALUES(?, ?)", (device, time.time())
        )


def status(device: str) -> dict:
    with _db() as c:
        d = c.execute("SELECT unlimited FROM devices WHERE id=?", (device,)).fetchone()
        row = c.execute(
            "SELECT COALESCE(SUM(units),0) u, COALESCE(SUM(heavy),0) h FROM usage "
            "WHERE device=? AND ts>=?",
            (device, _month_start()),
        ).fetchone()
    unlimited = bool(d and d["unlimited"])
    return {
        "unlimited": unlimited,
        "used": round(row["u"], 1),
        "allowance": None if unlimited else FREE_UNITS,
        "heavy_jobs": int(row["h"]),
        "exhausted": (not unlimited) and row["u"] >= FREE_UNITS,
    }


def _hash(code: str) -> str:
    return hashlib.sha256(code.strip().upper().encode()).hexdigest()


def mint(count: int) -> list[str]:
    """Create single-use lifetime keys. Plaintext is returned once, only hashes are stored."""
    codes = []
    with _lock, _db() as c:
        for _ in range(count):
            raw = secrets.token_hex(6).upper()
            code = f"VC-{raw[:4]}-{raw[4:8]}-{raw[8:]}"
            c.execute(
                "INSERT INTO keys(hash, created) VALUES(?, ?)", (_hash(code), time.time())
            )
            codes.append(code)
    return codes


def redeem(code: str, device: str) -> bool:
    """One-time redemption: grants unlimited access to the device forever."""
    with _lock, _db() as c:
        row = c.execute(
            "SELECT redeemed_by FROM keys WHERE hash=?", (_hash(code),)
        ).fetchone()
        if not row:
            return False
        if row["redeemed_by"]:
            return row["redeemed_by"] == device  # same device re-entering is fine
        c.execute(
            "UPDATE keys SET redeemed_by=?, redeemed_at=? WHERE hash=?",
            (device, time.time(), _hash(code)),
        )
        c.execute(
            "INSERT OR IGNORE INTO devices(id, created) VALUES(?, ?)", (device, time.time())
        )
        c.execute("UPDATE devices SET unlimited=1 WHERE id=?", (device,))
        return True


def grant(device: str):
    ensure_device(device)
    with _lock, _db() as c:
        c.execute("UPDATE devices SET unlimited=1 WHERE id=?", (device,))


class Meter:
    """Measures wall time, CPU time and peak RAM of this server process for one job."""

    def __enter__(self):
        self.p = psutil.Process()
        self.peak = 0
        self.stop = False
        self.t0 = time.time()
        self.c0 = self._cpu()
        self.th = threading.Thread(target=self._sample, daemon=True)
        self.th.start()
        return self

    def _cpu(self):
        t = self.p.cpu_times()
        return t.user + t.system

    def _sample(self):
        while not self.stop:
            try:
                rss = self.p.memory_info().rss
                for ch in self.p.children(recursive=True):
                    rss += ch.memory_info().rss
                self.peak = max(self.peak, rss)
            except Exception:
                pass
            time.sleep(0.2)

    def __exit__(self, *exc):
        self.stop = True
        self.th.join(timeout=1)
        self.wall = time.time() - self.t0
        self.cpu = self._cpu() - self.c0
        self.peak_gb = self.peak / 1024**3
        self.heavy = self.peak_gb > HEAVY_RAM_GB or self.cpu > HEAVY_CPU_SECONDS
        self.units = self.wall * (HEAVY_MULTIPLIER if self.heavy else 1.0)

    def record(self, device: str):
        with _lock, _db() as c:
            c.execute(
                "INSERT INTO usage(device, ts, wall, cpu, peak_gb, units, heavy) "
                "VALUES(?,?,?,?,?,?,?)",
                (device, time.time(), self.wall, self.cpu, self.peak_gb,
                 self.units, int(self.heavy)),
            )


if __name__ == "__main__":
    # python licensing.py mint 10   -> prints 10 single-use lifetime keys
    if len(sys.argv) == 3 and sys.argv[1] == "mint":
        print("\n".join(mint(int(sys.argv[2]))))
    else:
        print("usage: python licensing.py mint <count>")
