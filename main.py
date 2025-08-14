import os, json, sqlite3
from datetime import datetime
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

DB_PATH = os.path.join("/opt/render/project/src", "data.db")  # ruta válida en Render

def db():
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = db(); cur = conn.cursor()
    cur.execute("""CREATE TABLE IF NOT EXISTS settings(
        key TEXT PRIMARY KEY, value TEXT
    );""")
    cur.execute("""CREATE TABLE IF NOT EXISTS bets(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        event TEXT, bookmaker TEXT, market TEXT, selection TEXT,
        odds REAL, edge REAL, created_at TEXT, status TEXT DEFAULT 'active'
    );""")
    cur.execute("""CREATE TABLE IF NOT EXISTS history(
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        bet_id INTEGER, stake REAL, registered_at TEXT
    );""")
    defaults = {"kelly_fraction":"0.25","stake_min":"5","stake_max":"50","page_limit":"20"}
    for k,v in defaults.items():
        cur.execute("INSERT OR IGNORE INTO settings(key,value) VALUES(?,?)",(k,v))
    # semillas demo
    cur.execute("SELECT COUNT(*) c FROM bets WHERE status='active'")
    if cur.fetchone()["c"] == 0:
        now = datetime.utcnow().isoformat()
        demo = [
            ("Barcelona vs Real Madrid","Bet365","Ganador","Gana Barcelona",2.10,0.04),
            ("Lakers vs Celtics","Bet365","Handicap","Lakers -5",1.95,0.05),
            ("Arsenal vs Chelsea","Bet365","Over/Under","Over 2.5",1.92,0.035),
            ("PSG vs Lyon","Bet365","Ganador","Gana PSG",1.80,0.03),
            ("Juventus vs Inter","Bet365","Handicap","Inter +1.5",1.85,0.028),
        ]
        for e,bk,mkt,sel,od,ed in demo:
            cur.execute("""INSERT INTO bets(event,bookmaker,market,selection,odds,edge,created_at,status)
                        VALUES(?,?,?,?,?,?,?, 'active')""",(e,bk,mkt,sel,od,ed,now))
    conn.commit(); conn.close()

init_db()

app = FastAPI(title="Apuestas Backend MVP")

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

@app.get("/bets")
def list_bets():
    limit = int(get_setting("page_limit","20"))
    conn = db(); cur = conn.cursor()
    cur.execute("""SELECT id,event,bookmaker,market,selection,odds,edge,created_at
                   FROM bets WHERE status='active'
                   ORDER BY created_at DESC LIMIT ?""",(limit,))
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
