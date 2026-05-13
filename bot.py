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

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"})
    print(f"Telegram: {r.status_code} - {r.text[:100]}")
    return r

def get_fixtures():
    today = datetime.now(pytz.timezone("America/Argentina/Buenos_Aires")).strftime("%Y-%m-%d")
    print(f"Buscando partidos para: {today}")
    url = "https://v3.football.api-sports.io/fixtures"
    headers = {"x-apisports-key": API_FOOTBALL_KEY}
    params = {"date": today, "status": "NS"}
    r = requests.get(url, headers=headers, params=params)
    data = r.json().get("response", [])
    print(f"Partidos encontrados: {len(data)}")
    return data

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
    print("Iniciando analisis...")
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
        odd = get_odds(fid)
        if odd and float(odd["odd"]) <= 1.60:
            selections.append({
                "match": f"{home} vs {away}",
                "league": f"{country} - {league}",
                "bet": odd["value"],
                "odd": float(odd["odd"])
            })

    print(f"Selecciones encontradas: {len(selections)}")

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

print("Bot iniciando...")
print(f"Token: {TELEGRAM_TOKEN[:15] if TELEGRAM_TOKEN else 'NO TOKEN'}")
print(f"Chat ID: {TELEGRAM_CHAT_ID}")
send_telegram("Bot IvanPicks iniciado!")
analyze_and_send()

schedule.every().day.at("03:00").do(analyze_and_send)

while True:
    schedule.run_pending()
    time.sleep(60)
