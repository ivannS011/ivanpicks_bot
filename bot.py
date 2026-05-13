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
    "soccer_epl": ("\U0001f3f4\U000e0067\U000e0062\U000e0065\U000e006e\U000e0067\U000e007f", "Premier League", 39),
    "soccer_spain_la_liga": ("\U0001f1ea\U0001f1f8", "La Liga", 140),
    "soccer_germany_bundesliga": ("\U0001f1e9\U0001f1ea", "Bundesliga", 78),
    "soccer_italy_serie_a": ("\U0001f1ee\U0001f1f9", "Serie A", 135),
    "soccer_france_ligue_one": ("\U0001f1eb\U0001f1f7", "Ligue 1", 61),
    "soccer_uefa_champs_league": ("\U00002b50", "Champions League", 2),
    "soccer_uefa_europa_league": ("\U0001f7e0", "Europa League", 3),
    "soccer_argentina_primera_division": ("\U0001f1e6\U0001f1f7", "Liga Argentina", 128),
    "soccer_brazil_campeonato": ("\U0001f1e7\U0001f1f7", "Brasileirao", 71),
    "soccer_mexico_ligamx": ("\U0001f1f2\U0001f1fd", "Liga MX", 262),
    "soccer_usa_mls": ("\U0001f1fa\U0001f1f8", "MLS", 253),
    "soccer_portugal_primeira_liga": ("\U0001f1f5\U0001f1f9", "Primeira Liga", 94),
    "soccer_netherlands_eredivisie": ("\U0001f1f3\U0001f1f1", "Eredivisie", 88),
    "soccer_turkey_super_league": ("\U0001f1f9\U0001f1f7", "Super Lig", 203),
    "soccer_chile_campeonato": ("\U0001f1e8\U0001f1f1", "Liga Chile", 265),
    "soccer_colombia_primera_a": ("\U0001f1e8\U0001f1f4", "Liga Colombia", 239),
    "soccer_uruguay_primera_division": ("\U0001f1fa\U0001f1fe", "Liga Uruguay", 268),
    "soccer_conmebol_copa_libertadores": ("\U0001f30e", "Copa Libertadores", 13),
    "soccer_russia_premier_league": ("\U0001f1f7\U0001f1fa", "Premier Liga Rusia", 235),
    "soccer_saudi_arabias_league": ("\U0001f1f8\U0001f1e6", "Saudi Pro League", 307),
    "soccer_japan_j_league": ("\U0001f1ef\U0001f1f5", "J-League", 98),
    "soccer_scotland_premiership": ("\U0001f3f4\U000e0067\U000e0062\U000e0073\U000e0063\U000e0074\U000e007f", "Scottish Premiership", 179),
    "soccer_greece_super_league": ("\U0001f1ec\U0001f1f7", "Super League Grecia", 197),
    "soccer_belgium_first_div": ("\U0001f1e7\U0001f1ea", "Pro League Belgica", 144),
    "soccer_austria_bundesliga": ("\U0001f1e6\U0001f1f9", "Bundesliga Austria", 218),
    "soccer_switzerland_superleague": ("\U0001f1e8\U0001f1ed", "Super League Suiza", 207),
}

sent_picks = set()
api_football_cache = {}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={
        "chat_id": TELEGRAM_CHAT_ID,
        "text": message,
        "parse_mode": "HTML"
    })
    print(f"Telegram: {r.status_code}")
    return r

def get_team_stats(team_id, league_id, season=2024):
    cache_key = f"stats_{team_id}_{league_id}"
    if cache_key in api_football_cache:
        return api_football_cache[cache_key]
    try:
        url = "https://v3.football.api-sports.io/teams/statistics"
        headers = {"x-apisports-key": API_FOOTBALL_KEY}
        params = {"team": team_id, "league": league_id, "season": season}
        r = requests.get(url, headers=headers, params=params)
        data = r.json().get("response", {})
        api_football_cache[cache_key] = data
        return data
    except:
        return {}

def get_h2h(home_team, away_team):
    cache_key = f"h2h_{home_team}_{away_team}"
    if cache_key in api_football_cache:
        return api_football_cache[cache_key]
    try:
        url = "https://v3.football.api-sports.io/fixtures/headtohead"
        headers = {"x-apisports-key": API_FOOTBALL_KEY}
        params = {"h2h": f"{home_team}-{away_team}", "last": 10}
        r = requests.get(url, headers=headers, params=params)
        data = r.json().get("response", [])
        api_football_cache[cache_key] = data
        return data
    except:
        return []

def get_team_id(team_name, league_id):
    try:
        url = "https://v3.football.api-sports.io/teams"
        headers = {"x-apisports-key": API_FOOTBALL_KEY}
        params = {"name": team_name, "league": league_id, "season": 2024}
        r = requests.get(url, headers=headers, params=params)
        teams = r.json().get("response", [])
        if teams:
            return teams[0]["team"]["id"]
    except:
        pass
    return None

def analyze_with_api_football(home, away, league_id):
    result = {
        "avg_goals": 2.5,
        "avg_corners": 10,
        "avg_cards": 3,
        "home_form": 50,
        "away_form": 50,
        "btts_prob": 45,
        "over25_prob": 45,
        "corners_over95_prob": 45,
        "cards_over35_prob": 45,
    }
    try:
        home_id = get_team_id(home, league_id)
        away_id = get_team_id(away, league_id)

        if home_id:
            home_stats = get_team_stats(home_id, league_id)
            if home_stats:
                home_goals = home_stats.get("goals", {}).get("for", {}).get("average", {}).get("total", "2.5")
                home_corners = home_stats.get("fixtures", {}).get("played", {}).get("total", 1)
                result["home_form"] = min(float(str(home_goals).replace("-", "2.5")) * 20, 80)

        if away_id:
            away_stats = get_team_stats(away_id, league_id)
            if away_stats:
                away_goals = away_stats.get("goals", {}).get("for", {}).get("average", {}).get("total", "2.5")
                result["away_form"] = min(float(str(away_goals).replace("-", "2.5")) * 20, 80)

        h2h = get_h2h(home, away)
        if h2h:
            total_goals = sum(
                (g["goals"]["home"] or 0) + (g["goals"]["away"] or 0)
                for g in h2h if g["goals"]["home"] is not None
            )
            avg = total_goals / len(h2h)
            result["avg_goals"] = avg
            result["over25_prob"] = min(int((avg / 3) * 70), 80)
            btts = sum(1 for g in h2h if g["goals"]["home"] and g["goals"]["away"] and g["goals"]["home"] > 0 and g["goals"]["away"] > 0)
            result["btts_prob"] = int((btts / len(h2h)) * 100)

    except Exception as e:
        print(f"API-Football error: {e}")

    return result

def get_best_market(home, away, league_id, bookmakers, stats):
    candidates = []

    for bm in bookmakers:
        for market in bm.get("markets", []):
            key = market["key"]
            for outcome in market["outcomes"]:
                odd = float(outcome["price"])
                name = outcome["name"]
                implied_prob = round(1 / odd * 100, 1)

                stat_prob = implied_prob
                market_name = ""

                if key == "h2h":
                    if name == home:
                        stat_prob = stats["home_form"]
                        market_name = "Gana local"
                    elif name == away:
                        stat_prob = stats["away_form"]
                        market_name = "Gana visitante"
                    else:
                        market_name = "Empate"

                elif key == "totals":
                    if "Over" in name and "2.5" in name:
                        stat_prob = stats["over25_prob"]
                        market_name = "Mas de 2.5 goles"
                    elif "Under" in name and "2.5" in name:
                        stat_prob = 100 - stats["over25_prob"]
                        market_name = "Menos de 2.5 goles"
                    elif "Over" in name and "1.5" in name:
                        stat_prob = min(stats["over25_prob"] + 15, 85)
                        market_name = "Mas de 1.5 goles"
                    else:
                        market_name = name

                elif key == "btts":
                    if name == "Yes":
                        stat_prob = stats["btts_prob"]
                        market_name = "Ambos equipos marcan"
                    else:
                        stat_prob = 100 - stats["btts_prob"]
                        market_name = "No ambos marcan"

                value = stat_prob - implied_prob

                if odd >= 1.35 and odd <= 2.50 and stat_prob >= 55 and value >= 0:
                    candidates.append({
                        "bet": market_name or name,
                        "odd": odd,
                        "prob": stat_prob,
                        "implied": implied_prob,
                        "value": round(value, 1),
                        "market": key
                    })

    candidates.sort(key=lambda x: (x["prob"], x["value"]), reverse=True)
    return candidates[0] if candidates else None

def get_todays_picks():
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    print(f"Analizando partidos para: {today}")
    all_picks = []

    for sport_key, (flag, league_name, league_id) in LEAGUE_INFO.items():
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
                bookmakers = game.get("bookmakers", [])

                if not bookmakers:
                    continue

                stats = analyze_with_api_football(home, away, league_id)
                best = get_best_market(home, away, league_id, bookmakers, stats)

                if best:
                    all_picks.append({
                        "match": f"{home} vs {away}",
                        "league": f"{flag} {league_name}",
                        "bet": best["bet"],
                        "odd": best["odd"],
                        "prob": best["prob"],
                        "value": best["value"],
                    })

        except Exception as e:
            print(f"Error {sport_key}: {e}")
            continue

    all_picks.sort(key=lambda x: (x["prob"], x["value"]), reverse=True)
    unique = []
    seen = set()
    for p in all_picks:
        key = f"{p['match']}-{p['bet']}"
        if key not in seen:
            seen.add(key)
            unique.append(p)

    print(f"Picks encontrados: {len(unique)}")
    return unique[:10]

def send_picks(picks, title="Picks del dia"):
    if not picks:
        print("No hay picks suficientes")
        return

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

    for p in new_picks:
        sent_picks.add(f"{p['match']}-{p['bet']}")

def daily_analysis():
    print("Analisis diario 00:00...")
    sent_picks.clear()
    api_football_cache.clear()
    picks = get_todays_picks()
    send_picks(picks, "Picks del dia")

def check_new_opportunities():
    print("Revisando nuevas oportunidades...")
    picks = get_todays_picks()
    new = [p for p in picks if f"{p['match']}-{p['bet']}" not in sent_picks]
    if new:
        send_picks(new[:5], "Nueva oportunidad!")

print("Bot IvanPicks iniciando...")
send_telegram("\U0001f916 Bot IvanPicks iniciado y activo!")
daily_analysis()

schedule.every().day.at("03:00").do(daily_analysis)
schedule.every(2).hours.do(check_new_opportunities)

while True:
    schedule.run_pending()
    time.sleep(60)
