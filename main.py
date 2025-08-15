import os
import time
import requests
from datetime import datetime, timedelta
from typing import List, Optional, Dict, Any

from fastapi import FastAPI, Query, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ======================
# Configuración
# ======================
API_KEY = os.getenv("ODDS_API_KEY", "")
BASE = "https://api.the-odds-api.com/v4"

if not API_KEY:
    print("⚠️ ODDS_API_KEY no configurado. Ponlo en Render → Environment.")

# Caché simple en memoria para ahorrar requests (plan gratis)
CACHE_TTL = 120  # segundos
_cache: Dict[str, Dict[str, Any]] = {}  # {key: {"ts": epoch, "data": obj}}

def cache_get(key: str):
    now = time.time()
    item = _cache.get(key)
    if item and now - item["ts"] < CACHE_TTL:
        return item["data"]
    return None

def cache_set(key: str, data: Any):
    _cache[key] = {"ts": time.time(), "data": data}

# ======================
# FastAPI + CORS
# ======================
app = FastAPI(title="Apuestas Backend (Odds API)")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], allow_credentials=True,
    allow_methods=["*"], allow_headers=["*"],
)

# ======================
# Modelos
# ======================
class Bet(BaseModel):
    event: str
    bookmaker: str
    market: str
    selection: str
    odds: float
    edge: float
    sport: str
    start_time: str

# ======================
# Helpers The Odds API
# ======================

def api_get(path: str, params: dict = None):
    params = params or {}
    params["apiKey"] = API_KEY
    try:
        r = requests.get(f"{BASE}{path}", params=params, timeout=15)
        if r.status_code == 401:
            raise HTTPException(status_code=502, detail="API Key inválida o no configurada (401)")
        if r.status_code == 429:
            raise HTTPException(status_code=429, detail="Límite de peticiones alcanzado (429)")
        r.raise_for_status()
        return r.json()
    except requests.RequestException as e:
        raise HTTPException(status_code=502, detail=f"Error al contactar con The Odds API: {e}")

def list_sports() -> List[dict]:
    ck = "sports_all"
    cached = cache_get(ck)
    if cached: return cached
    data = api_get("/sports", params={"all": "true"})
    active = [s for s in data if s.get("active")]
    cache_set(ck, active)
    return active

def fetch_odds_for_sport(sport_key: str) -> List[dict]:
    ck = f"odds::{sport_key}"
    cached = cache_get(ck)
    if cached: return cached
    data = api_get(
        f"/sports/{sport_key}/odds",
        params={
            "regions": "eu",        # Europa
            "markets": "h2h",       # Ganador del partido
            "oddsFormat": "decimal" # Cuota decimal
        }
    )
    cache_set(ck, data)
    return data

def iso_to_dt(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))

def compute_edges(events: List[dict]) -> List[Bet]:
    out: List[Bet] = []
    imps_by_key: Dict[tuple, List[float]] = {}

    # Recolecta prob. implícitas por selección (consenso)
    for ev in events:
        event_id = ev.get("id") or f"{ev.get('home_team')}|{ev.get('away_team')}|{ev.get('commence_time')}"
        for bk in ev.get("bookmakers", []):
            for mkt in bk.get("markets", []):
                market_key = mkt.get("key", "h2h")
                for outcome in mkt.get("outcomes", []):
                    sel = outcome.get("name")
                    odds = float(outcome.get("price", 0.0) or 0.0)
                    if odds <= 1.0:
                        continue
                    implied = 1.0 / odds
                    key = (event_id, market_key, sel)
                    imps_by_key.setdefault(key, []).append(implied)

    def consensus(imps: List[float]) -> float:
        if not imps: return 0.0
        s = sorted(imps)
        n = len(s)
        return s[n//2] if n % 2 else 0.5 * (s[n//2 - 1] + s[n//2])

    # Genera apuestas con edge vs consenso
    for ev in events:
        start_iso = ev.get("commence_time")
        start_time = start_iso or datetime.utcnow().isoformat()
        sport_group = ev.get("sport_title") or ev.get("sport_key", "Sport")
        event_id = ev.get("id") or f"{ev.get('home_team')}|{ev.get('away_team')}|{start_time}"
        home = ev.get("home_team", "Home")
        away = ev.get("away_team", "Away")
        event_name = f"{home} vs {away}"

        for bk in ev.get("bookmakers", []):
            bk_name = bk.get("title", "Bookmaker")
            for mkt in bk.get("markets", []):
                market_key = mkt.get("key", "h2h")
                for outcome in mkt.get("outcomes", []):
                    sel = outcome.get("name")
                    odds = float(outcome.get("price", 0.0) or 0.0)
                    if odds <= 1.0:
                        continue
                    key = (event_id, market_key, sel)
                    p_cons = consensus(imps_by_key.get(key, []))
                    p_bk = 1.0 / odds
                    edge = p_cons - p_bk  # >0 sugiere valor relativo
                    out.append(Bet(
                        event=event_name,
                        bookmaker=bk_name,
                        market=market_key,
                        selection=sel,
                        odds=odds,
                        edge=edge,
                        sport=sport_group,
                        start_time=start_time
                    ))
    return out

# ======================
# Endpoints
# ======================

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat(), "backend_version": "oddsapi-v1"}

@app.get("/sports", response_model=List[str])
def get_sports():
    sports = list_sports()
    keys = [s["key"] for s in sports]
    priority = ["soccer_spain_la_liga", "soccer_epl", "soccer_uefa_champs_league", "basketball_nba", "tennis_atp"]
    keys_sorted = sorted(keys, key=lambda k: (k not in priority, k))
    return keys_sorted

@app.get("/bookmakers", response_model=List[str])
def get_bookmakers(sport_key: str = Query("soccer_epl")):
    events = fetch_odds_for_sport(sport_key)
    books = set()
    for ev in events:
        for bk in ev.get("bookmakers", []):
            title = bk.get("title")
            if title:
                books.add(title)
    return sorted(books)

@app.get("/bets", response_model=List[Bet])
def get_bets(
    sport_key: str = Query("soccer_epl"),
    bookmaker: Optional[str] = Query(None),
    hours_before: Optional[int] = Query(None, ge=0),
    edge_min: Optional[float] = Query(None),  # en %
    edge_max: Optional[float] = Query(None)   # en %
):
    events = fetch_odds_for_sport(sport_key)
    bets = compute_edges(events)

    if bookmaker:
        bets = [b for b in bets if b.bookmaker.lower() == bookmaker.lower()]
    if hours_before is not None:
        limit_dt = datetime.utcnow() + timedelta(hours=hours_before)
        bets = [b for b in bets if iso_to_dt(b.start_time) <= limit_dt]
    if edge_min is not None:
        thr = float(edge_min) / 100.0
        bets = [b for b in bets if b.edge >= thr]
    if edge_max is not None:
        thr = float(edge_max) / 100.0
        bets = [b for b in bets if b.edge <= thr]

    bets.sort(key=lambda b: b.edge, reverse=True)
    return bets[:200]
