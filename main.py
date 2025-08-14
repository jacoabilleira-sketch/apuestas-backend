import os, sqlite3
from datetime import datetime, timedelta
from typing import List, Optional
from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DB_PATH = os.path.join("/opt/render/project/src", "data.db")

def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def ensure_schema():
    conn = db(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY, value TEXT
    );""")
    cur.execute("""CREATE TABLE IF NOT EXISTS bets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event TEXT,
        bookmaker TEXT,
        market TEXT,
        selection TEXT,
        odds REAL,
        edge REAL,
        start_ts TEXT,     -- ISO fecha/hora del evento
        created_at TEXT,   -- cuándo detectamos la apuesta
        status TEXT DEFAULT 'active',
        sport TEXT DEFAULT ''
    );""")
    cur.execute("""CREATE TABLE IF NOT EXISTS history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bet_id INTEGER, stake REAL, registered_at TEXT
    );""")

    # Migraciones ligeras por si vienes de la versión anterior
    cols = {r["name"] for r in cur.execute("PRAGMA table_info(bets)").fetchall()}
    if "start_ts" not in cols:
        cur.execute("ALTER TABLE bets ADD COLUMN start_ts TEXT")
    if "sport" not in cols:
        cur.execute("ALTER TABLE bets ADD COLUMN sport TEXT DEFAULT ''")

    # Defaults
    defaults = {"kelly_fraction":"0.25","stake_min":"5","stake_max":"50","page_limit":"20"}
    for k,v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",(k,v))
    conn.commit(); conn.close()

def seed_demo():
    """Semillas con varias casas y horas distintas para probar filtros."""
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) c FROM bets WHERE status='active'")
    if cur.fetchone()["c"] == 0:
        now = datetime.utcnow()
        demos = [
            # (event, bookmaker, market, selection, odds, edge, start_ts, sport)
            ("Barcelona vs Real Madrid","Bet365","Ganador","Gana Barcelona",2.10,0.04, now+timedelta(hours=2), "Fútbol"),
            ("Lakers vs Celtics","Bet365","Handicap","Lakers -5",1.95,0.05, now+timedelta(hours=5), "Baloncesto"),
            ("Arsenal vs Chelsea","William Hill","Over/Under","Over 2.5",1.92,0.035, now+timedelta(hours=1), "Fútbol"),
            ("PSG vs Lyon","Pinnacle","Ganador","Gana PSG",1.80,0.03, now+timedelta(hours=7), "Fútbol"),
            ("Juventus vs Inter","Bwin","Handicap","Inter +1.5",1.85,0.028, now+timedelta(hours=8), "Fútbol"),
            ("Nadal vs Alcaraz","Bet365","Ganador","Gana Alcaraz",1.70,0.06, now+timedelta(hours=3), "Tenis"),
        ]
        for e,bk,mkt,sel,od,ed,st,sport in demos:
            cur.execute("""INSERT INTO bets(event,bookmaker,market,selection,odds,edge,start_ts,created_at,status,sport)
                           VALUES(?,?,?,?,?,?,?,?, 'active',?)""",
                        (e,bk,mkt,sel,od,ed, (st).isoformat(), now.isoformat(), sport))
        conn.commit()
    conn.close()

ensure_schema(); seed_demo()

app = FastAPI(title="Apuestas Backend (Filtros)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

class SettingsPayload(BaseModel):
    kelly_fraction: float
    stake_min: float
    stake_max: float
    page_limit: int

class RegisterPayload(BaseModel):
    bet_id: int
    stake: float

def get_setting(key: str, default: str):
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT value FROM settings WHERE key=?",(key,))
    row = cur.fetchone(); conn.close()
    return row["value"] if row else default

def set_setting(key: str, value: str):
    conn = db(); cur = conn.cursor()
    cur.execute("INSERT OR REPLACE INTO settings(key,value) VALUES(?,?)",(key,value))
    conn.commit(); conn.close()

@app.get("/health")
def health():
    return {"status":"ok","time": datetime.utcnow().isoformat()}

@app.get("/settings")
def get_settings():
    return {
        "kelly_fraction": float(get_setting("kelly_fraction","0.25")),
        "stake_min": float(get_setting("stake_min","5")),
        "stake_max": float(get_setting("stake_max","50")),
        "page_limit": int(get_setting("page_limit","20")),
    }

@app.post("/settings")
def save_settings(p: SettingsPayload):
    set_setting("kelly_fraction", str(p.kelly_fraction))
    set_setting("stake_min", str(p.stake_min))
    set_setting("stake_max", str(p.stake_max))
    set_setting("page_limit", str(p.page_limit))
    return {"ok": True}

@app.get("/bookmakers")
def bookmakers():
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT DISTINCT bookmaker FROM bets ORDER BY bookmaker")
    names = [r["bookmaker"] for r in cur.fetchall()]
    conn.close()
    return names

@app.get("/bets")
def list_bets(
    edge_min: float = Query(0.0, ge=-1, le=1),
    edge_max: float = Query(1.0, ge=-1, le=1),
    hours_max: int = Query(9999, ge=0),
    bookmakers: Optional[str] = None,  # coma-separado, ej: "Bet365,William Hill"
    limit: Optional[int] = None
):
    lim = int(limit or get_setting("page_limit","20"))
    now = datetime.utcnow()
    params = []
    where = ["status='active'"]

    where.append("edge BETWEEN ? AND ?")
    params.extend([edge_min, edge_max])

    if hours_max < 9999:
        where.append("(start_ts IS NULL OR (julianday(start_ts) - julianday(?)) * 24 <= ?)")
        params.extend([now.isoformat(), hours_max])

    if bookmakers:
        items = [x.strip() for x in bookmakers.split(",") if x.strip()]
        if items:
            placeholders = ",".join("?"*len(items))
            where.append(f"bookmaker IN ({placeholders})")
            params.extend(items)

    sql = f"""SELECT id,event,bookmaker,market,selection,odds,edge,start_ts,created_at,sport
              FROM bets
              WHERE {' AND '.join(where)}
              ORDER BY created_at DESC
              LIMIT ?"""
    params.append(lim)

    conn = db(); cur = conn.cursor()
    cur.execute(sql, params)
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

@app.post("/register")
def register(p: RegisterPayload):
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT * FROM bets WHERE id=? AND status='active'",(p.bet_id,))
    bet = cur.fetchone()
    if not bet:
        conn.close()
        raise HTTPException(status_code=404, detail="Apuesta no encontrada o ya registrada")
    cur.execute("UPDATE bets SET status='registered' WHERE id=?",(p.bet_id,))
    cur.execute("INSERT INTO history(bet_id,stake,registered_at) VALUES(?,?,?)",
                (p.bet_id, float(p.stake), datetime.utcnow().isoformat()))
    conn.commit(); conn.close()
    return {"ok": True}

@app.get("/history")
def history(limit: int = 50):
    conn = db(); cur = conn.cursor()
    cur.execute("""SELECT h.id, h.bet_id, h.stake, h.registered_at,
                          b.event, b.bookmaker, b.odds, b.edge
                   FROM history h
                   JOIN bets b ON b.id=h.bet_id
                   ORDER BY h.registered_at DESC
                   LIMIT ?""",(limit,))
    rows = [dict(r) for r in cur.fetchall()]
    conn.close()
    return rows

@app.get("/stats")
def stats():
    conn = db(); cur = conn.cursor()
    cur.execute("SELECT COUNT(*) c FROM bets WHERE status='active'")
    active = cur.fetchone()["c"]
    cur.execute("SELECT COUNT(*) c FROM bets WHERE status='registered'")
    registered = cur.fetchone()["c"]
    cur.execute("SELECT COALESCE(SUM(stake),0) s FROM history")
    staked = cur.fetchone()["s"]
    conn.close()
    # Nota: beneficio real requiere saber resultados; aquí mostramos acumulados básicos.
    return {"active": active, "registered": registered, "total_staked": staked}
