import os
import requests
from datetime import datetime
import pytz
import time
import schedule

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ODDS_API_KEY = os.environ.get("ODDS_API_KEY")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")

TZ = pytz.timezone("America/Argentina/Buenos_Aires")

LEAGUE_INFO = {
    "soccer_epl": ("\U0001f3f4", "Premier League", "ENG"),
    "soccer_spain_la_liga": ("\U0001f1ea\U0001f1f8", "La Liga", "ESP"),
    "soccer_germany_bundesliga": ("\U0001f1e9\U0001f1ea", "Bundesliga", "GER"),
    "soccer_italy_serie_a": ("\U0001f1ee\U0001f1f9", "Serie A", "ITA"),
    "soccer_france_ligue_one": ("\U0001f1eb\U0001f1f7", "Ligue 1", "FRA"),
    "soccer_uefa_champs_league": ("\U00002b50", "Champions League", "EUR"),
    "soccer_uefa_europa_league": ("\U0001f7e0", "Europa League", "EUR"),
    "soccer_argentina_primera_division": ("\U0001f1e6\U0001f1f7", "Liga Argentina", "ARG"),
    "soccer_brazil_campeonato": ("\U0001f1e7\U0001f1f7", "Brasileirao", "BRA"),
    "soccer_mexico_ligamx": ("\U0001f1f2\U0001f1fd", "Liga MX", "MEX"),
    "soccer_usa_mls": ("\U0001f1fa\U0001f1f8", "MLS", "USA"),
    "soccer_portugal_primeira_liga": ("\U0001f1f5\U0001f1f9", "Primeira Liga", "POR"),
    "soccer_netherlands_eredivisie": ("\U0001f1f3\U0001f1f1", "Eredivisie", "NED"),
    "soccer_turkey_super_league": ("\U0001f1f9\U0001f1f7", "Super Lig", "TUR"),
    "soccer_chile_campeonato": ("\U0001f1e8\U0001f1f1", "Primera Division Chile", "CHI"),
    "soccer_colombia_primera_a": ("\U0001f1e8\U0001f1f4", "Liga Colombia", "COL"),
    "soccer_uruguay_primera_division": ("\U0001f1fa\U0001f1fe", "Primera Division Uruguay", "URU"),
}

sent_picks = set()

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    })
    print(f"Telegram: {r.status_code}")
    return r

def get_team_stats(team_name, league_id, season=2024):
    try:
        url = "https://v3.football.api-sports.io/teams/statistics"
        headers = {"x-apisports-key": API_FOOTBALL_KEY}
        params = {"team": team_name, "league": league_id, "season": season}
        r = requests.get(url, headers=headers, params=params)
        return r.json().get("response", {})
    except:
        return {}

def get_h2h(home_team, away_team):
    try:
        url = "https://v3.football.api-sports.io/fixtures/headtohead"
        headers = {"x-apisports-key": API_FOOTBALL_KEY}
        params = {"h2h": f"{home_team}-{away_team}", "last": 10}
        r = requests.get(url, headers=headers, params=params)
        return r.json().get("response", [])
    except:
        return []

def calculate_probability(home, away, sport_key):
    score = 50
    flag, league_name, _ = LEAGUE_INFO.get(sport_key, ("", sport_key, ""))

    # Análisis H2H
    h2h = get_h2h(home, away)
    if h2h:
        home_wins = sum(1 for g in h2h if g["teams"]["home"]["name"] == home and g["teams"]["home"]["winner"])
        away_wins = sum(1 for g in h2h if g["teams"]["away"]["name"] == away and g["teams"]["away"]["winner"])
        total_goals = sum(g["goals"]["home"] + g["goals"]["away"] for g in h2h if g["goals"]["home"] is not None)
        avg_goals = total_goals / len(h2h) if h2h else 2.5

        # Ajustar probabilidad según H2H
        if home_wins > away_wins:
            score += 10
        if avg_goals > 2.5:
            score += 5
        if avg_goals < 2.0:
            score -= 5

    return min(score, 95)

def analyze_match(home, away, sport_key, bookmakers):
    flag, league_name, _ = LEAGUE_INFO.get(sport_key, ("\U0001f3c6", sport_key, ""))
    prob = calculate_probability(home, away, sport_key)

    picks = []

    for bm in bookmakers:
        for market in bm.get("markets", []):
            key = market["key"]
            for outcome in market["outcomes"]:
                odd = float(outcome["price"])
                name = outcome["name"]

                # Calcular valor esperado
                implied_prob = 1 / odd * 100
                value = prob - implied_prob

                # Solo picks con buena probabilidad y valor
                if odd >= 1.40 and odd <= 2.20 and implied_prob >= 45:
                    picks.append({
                        "match": f"{home} vs {away}",
                        "league": f"{flag} {league_name}",
                        "market": key,
                        "bet": name,
                        "odd": odd,
                        "prob": round(implied_prob, 1),
                        "value": round(value, 1)
                    })

    # Ordenar por probabilidad
    picks.sort(key=lambda x: x["prob"], reverse=True)
    return picks[:2] if picks else []

def get_todays_picks():
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    print(f"Analizando partidos para: {today}")

    all_picks = []

    for sport_key in LEAGUE_INFO.keys():
        try:
            url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
            params = {
                "apiKey": ODDS_API_KEY,
                "regions": "eu",
                "markets": "h2h,totals,btts",
                "oddsFormat": "decimal",
            }
            r = requests.get(url, params=params)
            if r.status_code != 200:
                continue

            games = r.json()
            for game in games:
                if today not in game.get("commence_time", ""):
                    continue
                home = game["home_team"]
                away = game["away_team"]
                picks = analyze_match(home, away, sport_key, game.get("bookmakers", []))
                all_picks.extend(picks)
        except Exception as e:
            print(f"Error {sport_key}: {e}")
            continue

    # Ordenar por probabilidad y eliminar duplicados
    all_picks.sort(key=lambda x: x["prob"], reverse=True)
    unique = []
    seen = set()
    for p in all_picks:
        key = f"{p['match']}-{p['bet']}"
        if key not in seen:
            seen.add(key)
            unique.append(p)

    return unique[:10]

def send_picks(picks, title="Picks del dia"):
    if not picks:
        print("No hay picks suficientes")
        return

    # Verificar si ya se enviaron
    new_picks = [p for p in picks if f"{p['match']}-{p['bet']}" not in sent_picks]
    if not new_picks:
        print("No hay picks nuevos")
        return

    casa = "\U0001f7e2 STAKE" if len(new_picks) > 5 else "\U0001f535 1XBET"
    msg = f"\U0001f3af <b>IVANPICKS - {title}</b>\n"
    msg += f"\U0001f4c5 {datetime.now(TZ).strftime('%d/%m/%Y %H:%M')}\n"
    msg += f"\U0001f3e6 Casa recomendada: {casa}\n\n"

    for i, p in enumerate(new_picks, 1):
        msg += f"<b>Pick {i}</b>\n"
        msg += f"\u26bd {p['match']}\n"
        msg += f"\U0001f3c6 {p['league']}\n"
        msg += f"\u2705 Apuesta: {p['bet']}\n"
        msg += f"\U0001f4b0 Cuota: {p['odd']}\n"
        msg += f"\U0001f4ca Probabilidad: {p['prob']}%\n\n"

    msg += "\u26a0\ufe0f Aposta con responsabilidad."
    send_telegram(msg)

    # Marcar como enviados
    for p in new_picks:
        sent_picks.add(f"{p['match']}-{p['bet']}")

def daily_analysis():
    print("Analisis diario 00:00...")
    sent_picks.clear()
    picks = get_todays_picks()
    send_picks(picks, "Picks del dia")

def check_new_opportunities():
    print("Revisando nuevas oportunidades...")
    picks = get_todays_picks()
    new = [p for p in picks if f"{p['match']}-{p['bet']}" not in sent_picks]
    if new:
        send_picks(new[:5], "Nueva oportunidad detectada!")

# Arranque inicial
print("Bot IvanPicks iniciando...")
send_telegram("\U0001f916 Bot IvanPicks iniciado y activo!")
daily_analysis()

# Programar tareas
schedule.every().day.at("03:00").do(daily_analysis)  # 00:00 Argentina = 03:00 UTC
schedule.every(2).hours.do(check_new_opportunities)

while True:
    schedule.run_pending()
    time.sleep(60)
