import os
from datetime import datetime, timedelta
from typing import List

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Simulación de datos
# (Aquí iría la lógica real para leer de tu base o API externa)
DUMMY_BETS = [
    {
        "event": "Equipo A vs Equipo B",
        "bookmaker": "Bet365",
        "market": "1X2",
        "selection": "Equipo A",
        "odds": 2.10,
        "edge": 0.07,
        "sport": "Fútbol",
        "start_time": (datetime.utcnow() + timedelta(hours=2)).isoformat()
    },
    {
        "event": "Jugador X vs Jugador Y",
        "bookmaker": "William Hill",
        "market": "Ganador",
        "selection": "Jugador Y",
        "odds": 1.80,
        "edge": 0.05,
        "sport": "Tenis",
        "start_time": (datetime.utcnow() + timedelta(hours=5)).isoformat()
    }
]

# --- FastAPI ---
app = FastAPI()

# Permitir CORS para que Netlify pueda acceder
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Modelos ---
class Bet(BaseModel):
    event: str
    bookmaker: str
    market: str
    selection: str
    odds: float
    edge: float
    sport: str
    start_time: str

# --- Endpoints ---
@app.get("/sports", response_model=List[str])
def get_sports():
    sports = sorted(set(bet["sport"] for bet in DUMMY_BETS))
    return sports

@app.get("/bookmakers", response_model=List[str])
def get_bookmakers():
    books = sorted(set(bet["bookmaker"] for bet in DUMMY_BETS))
    return books

@app.get("/bets", response_model=List[Bet])
def get_bets(
    sport: str = Query(None),
    bookmaker: str = Query(None),
    hours_before: int = Query(None),
    edge_min: float = Query(None),
    edge_max: float = Query(None)
):
    bets = DUMMY_BETS
    if sport:
        bets = [b for b in bets if b["sport"].lower() == sport.lower()]
    if bookmaker:
        bets = [b for b in bets if b["bookmaker"].lower() == bookmaker.lower()]
    if hours_before is not None:
        limit_time = datetime.utcnow() + timedelta(hours=hours_before)
        bets = [b for b in bets if datetime.fromisoformat(b["start_time"]) <= limit_time]
    if edge_min is not None:
        bets = [b for b in bets if b["edge"] >= edge_min / 100]
    if edge_max is not None:
        bets = [b for b in bets if b["edge"] <= edge_max / 100]
    return bets

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}
