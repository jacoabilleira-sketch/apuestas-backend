import os
import requests
from datetime import datetime, timedelta
from typing import List

from fastapi import FastAPI, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ======================
# Configuración API Externa
# ======================
API_URL = "https://api.the-odds-api.com/v4/sports"
API_KEY = os.getenv("ODDS_API_KEY", "")  # Variable de entorno

if not API_KEY:
    print("⚠️ ODDS_API_KEY no configurado. Añádelo en Render.")

# ======================
# FastAPI
# ======================
app = FastAPI()

# Permitir CORS para que Netlify pueda acceder
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
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
# Funciones auxiliares
# ======================
def fetch_real_bets():
    try:
        sport_key = "soccer_epl"  # Cambiar aquí si quieres otra liga/deporte
        resp = requests.get(
            f"{API_URL}/{sport_key}/odds",
            params={
                "apiKey": API_KEY,
                "regions": "eu",        # Europa
                "markets": "h2h",       # Ganador del partido
                "oddsFormat": "decimal" # Cuotas decimales
            }
        )
        data = resp.json()
        
        bets = []
        for event in data:
            for bookmaker in event.get("bookmakers", []):
                for market in bookmaker.get("markets", []):
                    for outcome in market.get("outcomes", []):
                        bets.append({
                            "event": f"{event['home_team']} vs {event['away_team']}",
                            "bookmaker": bookmaker["title"],
                            "market": market["key"],
                            "selection": outcome["name"],
                            "odds": outcome["price"],
                            "edge": 0.05,  # Valor fijo por ahora
                            "sport": "Fútbol",
                            "start_time": event["commence_time"]
                        })
        return bets
    except Exception as e:
        print("Error al obtener datos de API:", e)
        return []

# ======================
# Endpoints
# ======================
@app.get("/sports", response_model=List[str])
def get_sports():
    return ["Fútbol"]  # De momento fijo

@app.get("/bookmakers", response_model=List[str])
def get_bookmakers():
    bets = fetch_real_bets()
    books = sorted(set(b["bookmaker"] for b in bets))
    return books

@app.get("/bets", response_model=List[Bet])
def get_bets(
    sport: str = Query(None),
    bookmaker: str = Query(None),
    hours_before: int = Query(None),
    edge_min: float = Query(None),
    edge_max: float = Query(None)
):
    bets = fetch_real_bets()
    if sport:
        bets = [b for b in bets if b["sport"].lower() == sport.lower()]
    if bookmaker:
        bets = [b for b in bets if b["bookmaker"].lower() == bookmaker.lower()]
    if hours_before is not None:
        limit_time = datetime.utcnow() + timedelta(hours=hours_before)
        bets = [b for b in bets if datetime.fromisoformat(b["start_time"].replace("Z", "+00:00")) <= limit_time]
    if edge_min is not None:
        bets = [b for b in bets if b["edge"] >= edge_min / 100]
    if edge_max is not None:
        bets = [b for b in bets if b["edge"] <= edge_max / 100]
    return bets

@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}
