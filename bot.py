import os
import requests
from datetime import datetime
import pytz
import time
import schedule

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
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
    "USA": "\U0001f1fa\U0001f1f8",
    "Mexico": "\U0001f1f2\U0001f1fd",
    "Chile": "\U0001f1e8\U0001f1f1",
    "Colombia": "\U0001f1e8\U0001f1f4",
    "Uruguay": "\U0001f1fa\U0001f1fe",
    "Turkey": "\U0001f1f9\U0001f1f7",
    "Greece": "\U0001f1ec\U0001f1f7",
    "Japan": "\U0001f1ef\U0001f1f5",
    "Australia": "\U0001f1e6\U0001f1fa",
}

LEAGUE_FLAGS = {
    "soccer_epl": ("\U0001f3f4", "Premier League"),
    "soccer_spain_la_liga": ("\U0001f1ea\U0001f1f8", "La Liga"),
    "soccer_germany_bundesliga": ("\U0001f1e9\U0001f1ea", "Bundesliga"),
    "soccer_italy_serie_a": ("\U0001f1ee\U0001f1f9", "Serie A"),
    "soccer_france_ligue_one": ("\U0001f1eb\U0001f1f7", "Ligue 1"),
    "soccer_uefa_champs_league": ("\U0001f1ea\U0001f1fa", "Champions League"),
    "soccer_uefa_europa_league": ("\U0001f1ea\U0001f1fa", "Europa League"),
    "soccer_argentina_primera_division": ("\U0001f1e6\U0001f1f7", "Liga Argentina"),
    "soccer_brazil_campeonato": ("\U0001f1e7\U0001f1f7", "Brasileirao"),
    "soccer_mexico_ligamx": ("\U0001f1f2\U0001f1fd", "Liga MX"),
    "soccer_usa_mls": ("\U0001f1fa\U0001f1f8", "MLS"),
    "soccer_portugal_primeira_liga": ("\U0001f1f5\U0001f1f9", "Primeira Liga"),
    "soccer_netherlands_eredivisie": ("\U0001f1f3\U0001f1f1", "Eredivisie"),
    "soccer_turkey_super_league": ("\U0001f1f9\U0001f1f7", "Super Lig"),
}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    })
    print(f"Telegram: {r.status_code}")
    return r

def get_sports():
    url = "https://api.the-odds-api.com/v4/sports"
    params = {"apiKey": ODDS_API_KEY}
    r = requests.get(url, params=params)
    return [s["key"] for s in r.json() if s.get("group") == "Soccer" and s.get("active")]

def get_odds_for_sport(sport_key):
    url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
    params = {
        "apiKey": ODDS_API_KEY,
        "regions": "eu",
        "markets": "h2h",
        "oddsFormat": "decimal",
        "bookmakers": "stake,betway,unibet"
    }
    r = requests.get(url, params=params)
    if r.status_code != 200:
        return []
    return r.json()

def analyze_and_send():
    print("Iniciando analisis...")
    tz = pytz.timezone("America/Argentina/Buenos_Aires")
    today = datetime.now(tz).strftime("%Y-%m-%d")
    print(f"Fecha: {today}")

    sports = list(LEAGUE_FLAGS.keys())
    all_selections = []

    for sport_key in sports:
        games = get_odds_for_sport(sport_key)
        flag, league_name = LEAGUE_FLAGS.get(sport_key, ("", sport_key))

        for game in games:
            game_time = game.get("commence_time", "")
            if today not in game_time:
                continue

            home = game.get("home_team", "")
            away = game.get("away_team", "")
            bookmakers = game.get("bookmakers", [])

            best_odd = None
            best_outcome = None

            for bm in bookmakers:
                for market in bm.get("markets", []):
                    if market["key"] == "h2h":
                        for outcome in market["outcomes"]:
                            odd = float(outcome["price"])
                            if odd <= 1.60:
                                if best_odd is None or odd < best_odd:
                                    best_odd = odd
                                    best_outcome = outcome["name"]

            if best_odd and best_outcome:
                all_selections.append({
                    "match": f"{home} vs {away}",
                    "league": f"{flag} {league_name}",
                    "bet": best_outcome,
                    "odd": best_odd
                })

    print(f"Selecciones encontradas: {len(all_selections)}")

    if not all_selections:
        send_telegram("Hoy no hay picks con probabilidad suficiente.")
        return

    all_selections.sort(key=lambda x: x["odd"])
    selections = all_selections[:10]
    avg_odd = sum(s["odd"] for s in selections) / len(selections)
    casa = "STAKE" if len(selections) > 5 else "1XBET"

    msg = "<b>IVANPICKS - Picks del dia</b>\n"
    msg += f"Fecha: {datetime.now(tz).strftime('%d/%m/%Y')}\n"
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
    print("Picks enviados!")

print("Bot iniciando...")
send_telegram("Bot IvanPicks iniciado!")
analyze_and_send()

schedule.every().day.at("03:00").do(analyze_and_send)

while True:
    schedule.run_pending()
    time.sleep(60)
