import os
import requests
from datetime import datetime
import pytz
import time
import schedule

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")
ODDS_API_KEY = os.environ.get("ODDS_API_KEY")

COUNTRY_FLAGS = {
    "Argentina": "\U0001f1e6\U0001f1f7",
    "Brazil": "\U0001f1e7\U0001f1f7",
    "England": "\U0001f3f4",
    "Spain": "\U0001f1ea\U0001f1f8",
    "Germany": "\U0001f1e9\U0001f1ea",
    "France": "\U0001f1eb\U0001f1f7",
    "Italy": "\U0001f1ee\U0001f1f9",
    "Portugal": "\U0001f1f5\U0001f1f9",
    "Netherlands": "\U0001f1f3\U0001f1f1",
    "Belgium": "\U0001f1e7\U0001f1ea",
    "Uruguay": "\U0001f1fa\U0001f1fe",
    "Chile": "\U0001f1e8\U0001f1f1",
    "Colombia": "\U0001f1e8\U0001f1f4",
    "Mexico": "\U0001f1f2\U0001f1fd",
    "USA": "\U0001f1fa\U0001f1f8",
    "Japan": "\U0001f1ef\U0001f1f5",
    "South Korea": "\U0001f1f0\U0001f1f7",
    "Turkey": "\U0001f1f9\U0001f1f7",
    "Greece": "\U0001f1ec\U0001f1f7",
    "Poland": "\U0001f1f5\U0001f1f1",
    "Croatia": "\U0001f1ed\U0001f1f7",
    "Switzerland": "\U0001f1e8\U0001f1ed",
    "Denmark": "\U0001f1e9\U0001f1f0",
    "Sweden": "\U0001f1f8\U0001f1ea",
    "Norway": "\U0001f1f3\U0001f1f4",
    "Ukraine": "\U0001f1fa\U0001f1e6",
    "Morocco": "\U0001f1f2\U0001f1e6",
    "Egypt": "\U0001f1ea\U0001f1ec",
    "Nigeria": "\U0001f1f3\U0001f1ec",
    "Ecuador": "\U0001f1ea\U0001f1e8",
    "Paraguay": "\U0001f1f5\U0001f1fe",
    "Peru": "\U0001f1f5\U0001f1ea",
    "Venezuela": "\U0001f1fb\U0001f1ea",
}

def get_flag(country):
    return COUNTRY_FLAGS.get(country, "")

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"})

def get_fixtures():
    today = datetime.now(pytz.timezone("America/Argentina/Buenos_Aires")).strftime("%Y-%m-%d")
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    params = {"date": today, "status": "NS"}
    r = requests.get(url, headers=headers, params=params)
    return r.json().get("response", [])

def get_odds(fixture_id):
    url = "https://v3.football.api-sports.io/odds"
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    params = {"fixture": fixture_id, "bookmaker": 8}
    r = requests.get(url, headers=headers, params=params)
    data = r.json().get("response", [])
    if not data:
        return None
    try:
        bets = data[0]["bookmakers"][0]["bets"]
        for bet in bets:
            if bet["name"] == "Match Winner":
                values = bet["values"]
                best = min(values, key=lambda x: float(x["odd"]))
                return best
    except:
        return None

def analyze_and_send():
    fixtures = get_fixtures()
    selections = []
    for f in fixtures:
        if len(selections) >= 10:
            break
        fid = f["fixture"]["id"]
        home = f["teams"]["home"]["name"]
        away = f["teams"]["away"]["name"]
        league = f["league"]["name"]
        country = f["league"]["country"]
        flag = get_flag(country)
        odd = get_odds(fid)
        if odd and float(odd["odd"]) <= 1.60:
            selections.append({
                "match": f"{home} vs {away}",
                "league": f"{flag} {country} - {league}",
                "bet": odd["value"],
                "odd": float(odd["odd"])
            })

    if not selections:
        send_telegram("Hoy no hay picks con probabilidad suficiente.")
        return

    selections.sort(key=lambda x: x["odd"])
    selections = selections[:10]
    avg_odd = sum(s["odd"] for s in selections) / len(selections)
    casa = "STAKE" if len(selections) > 5 else "1XBET"

    msg = "<b>IVANPICKS - Picks del dia</b>\n"
    msg += f"Fecha: {datetime.now(pytz.timezone('America/Argentina/Buenos_Aires')).strftime('%d/%m/%Y')}\n"
    msg += f"Casa recomendada: {casa}\n\n"
    for i, s in enumerate(selections, 1):
        msg += f"<b>Pick {i}</b>\n"
        msg += f"Partido: {s['match']}\n"
        msg += f"Liga: {s['league']}\n"
        msg += f"Apuesta: {s['bet']}\n"
        msg += f"Cuota: {s['odd']}\n\n"
    msg += f"Cuota promedio: {avg_odd:.2f}\n"
    msg += "Aposta con responsabilidad."
    send_telegram(msg)

schedule.every().day.at("03:00").do(analyze_and_send)
send_telegram("Bot IvanPicks iniciado!")
analyze_and_send()

while True:
    schedule.run_pending()
    time.sleep(60)
