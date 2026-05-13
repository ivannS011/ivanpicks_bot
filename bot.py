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
cache = {}

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"})
    print(f"Telegram: {r.status_code}")
    return r

def api_football_get(endpoint, params):
    cache_key = f"{endpoint}_{str(params)}"
    if cache_key in cache:
        return cache[cache_key]
    try:
        url = f"https://v3.football.api-sports.io/{endpoint}"
        headers = {"x-apisports-key": API_FOOTBALL_KEY}
        r = requests.get(url, headers=headers, params=params)
        data = r.json().get("response", [])
        cache[cache_key] = data
        return data
    except:
        return []

def get_team_id(team_name, league_id):
    data = api_football_get("teams", {"name": team_name, "league": league_id, "season": 2024})
    if data:
        return data[0]["team"]["id"]
    return None

def get_fixtures_stats(team_id, league_id):
    data = api_football_get("teams/statistics", {"team": team_id, "league": league_id, "season": 2024})
    return data if data else {}

def get_h2h(home, away):
    data = api_football_get("fixtures/headtohead", {"h2h": f"{home}-{away}", "last": 10})
    return data if data else []

def analyze_corners_cards(home, away, league_id):
    result = {
        "corners_avg": 10.0,
        "cards_avg": 3.5,
        "corners_over95_prob": 50,
        "corners_over105_prob": 40,
        "cards_over35_prob": 50,
        "cards_over45_prob": 35,
        "home_corners_avg": 5.0,
        "away_corners_avg": 5.0,
    }
    try:
        home_id = get_team_id(home, league_id)
        away_id = get_team_id(away, league_id)

        h2h = get_h2h(home, away)
        if h2h:
            corners_list = []
            cards_list = []
            for g in h2h:
                stats = g.get("statistics", [])
                home_corners = 0
                away_corners = 0
                home_cards = 0
                away_cards = 0
                for s in stats:
                    if s["type"] == "Corner Kicks":
                        if s["team"]["name"] == home:
                            home_corners = int(s["value"] or 0)
                        else:
                            away_corners = int(s["value"] or 0)
                    if s["type"] == "Yellow Cards":
                        if s["team"]["name"] == home:
                            home_cards = int(s["value"] or 0)
                        else:
                            away_cards = int(s["value"] or 0)
                total_corners = home_corners + away_corners
                total_cards = home_cards + away_cards
                if total_corners > 0:
                    corners_list.append(total_corners)
                if total_cards > 0:
                    cards_list.append(total_cards)

            if corners_list:
                avg_c = sum(corners_list) / len(corners_list)
                result["corners_avg"] = round(avg_c, 1)
                result["corners_over95_prob"] = int(sum(1 for c in corners_list if c > 9.5) / len(corners_list) * 100)
                result["corners_over105_prob"] = int(sum(1 for c in corners_list if c > 10.5) / len(corners_list) * 100)

            if cards_list:
                avg_k = sum(cards_list) / len(cards_list)
                result["cards_avg"] = round(avg_k, 1)
                result["cards_over35_prob"] = int(sum(1 for k in cards_list if k > 3.5) / len(cards_list) * 100)
                result["cards_over45_prob"] = int(sum(1 for k in cards_list if k > 4.5) / len(cards_list) * 100)

    except Exception as e:
        print(f"Error corners/cards: {e}")

    return result

def get_goals_stats(home, away):
    result = {
        "avg_goals": 2.5,
        "over25_prob": 45,
        "over15_prob": 65,
        "btts_prob": 45,
        "home_form": 50,
        "away_form": 50,
    }
    try:
        h2h = get_h2h(home, away)
        if h2h:
            goals_list = []
            btts_count = 0
            for g in h2h:
                hg = g["goals"]["home"] or 0
                ag = g["goals"]["away"] or 0
                goals_list.append(hg + ag)
                if hg > 0 and ag > 0:
                    btts_count += 1

            if goals_list:
                avg = sum(goals_list) / len(goals_list)
                result["avg_goals"] = round(avg, 1)
                result["over25_prob"] = int(sum(1 for g in goals_list if g > 2.5) / len(goals_list) * 100)
                result["over15_prob"] = int(sum(1 for g in goals_list if g > 1.5) / len(goals_list) * 100)
                result["btts_prob"] = int(btts_count / len(h2h) * 100)
    except Exception as e:
        print(f"Error goals stats: {e}")
    return result

def get_best_market_with_odds(home, away, bookmakers, goals_stats):
    candidates = []
    for bm in bookmakers:
        for market in bm.get("markets", []):
            key = market["key"]
            for outcome in market["outcomes"]:
                odd = float(outcome["price"])
                name = outcome["name"]
                implied_prob = round(1 / odd * 100, 1)
                stat_prob = implied_prob
                market_name = name

                if key == "h2h":
                    if name == home:
                        stat_prob = goals_stats["home_form"]
                        market_name = f"Gana {home}"
                    elif name == away:
                        stat_prob = goals_stats["away_form"]
                        market_name = f"Gana {away}"
                    else:
                        market_name = "Empate"

                elif key == "totals":
                    if "Over" in name and "2.5" in name:
                        stat_prob = goals_stats["over25_prob"]
                        market_name = "Mas de 2.5 goles"
                    elif "Under" in name and "2.5" in name:
                        stat_prob = 100 - goals_stats["over25_prob"]
                        market_name = "Menos de 2.5 goles"
                    elif "Over" in name and "1.5" in name:
                        stat_prob = goals_stats["over15_prob"]
                        market_name = "Mas de 1.5 goles"

                elif key == "btts":
                    if name == "Yes":
                        stat_prob = goals_stats["btts_prob"]
                        market_name = "Ambos equipos marcan"
                    else:
                        stat_prob = 100 - goals_stats["btts_prob"]
                        market_name = "No ambos marcan"

                value = stat_prob - implied_prob
                if odd >= 1.35 and odd <= 2.50 and stat_prob >= 55 and value >= 0:
                    candidates.append({
                        "bet": market_name,
                        "odd": odd,
                        "prob": stat_prob,
                        "value": round(value, 1),
                    })

    candidates.sort(key=lambda x: (x["prob"], x["value"]), reverse=True)
    return candidates[0] if candidates else None

def get_todays_picks():
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    print(f"Analizando partidos para: {today}")
    main_picks = []
    stats_picks = []

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

                # Picks con cuotas
                goals_stats = get_goals_stats(home, away)
                best = get_best_market_with_odds(home, away, bookmakers, goals_stats)
                if best:
                    main_picks.append({
                        "match": f"{home} vs {away}",
                        "league": f"{flag} {league_name}",
                        "bet": best["bet"],
                        "odd": best["odd"],
                        "prob": best["prob"],
                        "type": "main"
                    })

                # Picks solo probabilidad (corners/tarjetas)
                cc_stats = analyze_corners_cards(home, away, league_id)
                if cc_stats["corners_over95_prob"] >= 65:
                    stats_picks.append({
                        "match": f"{home} vs {away}",
                        "league": f"{flag} {league_name}",
                        "bet": "Mas de 9.5 corners",
                        "prob": cc_stats["corners_over95_prob"],
                        "avg": cc_stats["corners_avg"],
                        "type": "stats"
                    })
                if cc_stats["corners_over105_prob"] >= 60:
                    stats_picks.append({
                        "match": f"{home} vs {away}",
                        "league": f"{flag} {league_name}",
                        "bet": "Mas de 10.5 corners",
                        "prob": cc_stats["corners_over105_prob"],
                        "avg": cc_stats["corners_avg"],
                        "type": "stats"
                    })
                if cc_stats["cards_over35_prob"] >= 65:
                    stats_picks.append({
                        "match": f"{home} vs {away}",
                        "league": f"{flag} {league_name}",
                        "bet": "Mas de 3.5 tarjetas",
                        "prob": cc_stats["cards_over35_prob"],
                        "avg": cc_stats["cards_avg"],
                        "type": "stats"
                    })

        except Exception as e:
            print(f"Error {sport_key}: {e}")
            continue

    main_picks.sort(key=lambda x: x["prob"], reverse=True)
    stats_picks.sort(key=lambda x: x["prob"], reverse=True)

    seen = set()
    unique_main = []
    for p in main_picks:
        k = f"{p['match']}-{p['bet']}"
        if k not in seen:
            seen.add(k)
            unique_main.append(p)

    unique_stats = []
    for p in stats_picks:
        k = f"{p['match']}-{p['bet']}"
        if k not in seen:
            seen.add(k)
            unique_stats.append(p)

    print(f"Picks con cuota: {len(unique_main)} | Picks estadisticas: {len(unique_stats)}")
    return unique_main[:10], unique_stats[:5]

def send_picks(main_picks, stats_picks, title="Picks del dia"):
    new_main = [p for p in main_picks if f"{p['match']}-{p['bet']}" not in sent_picks]
    new_stats = [p for p in stats_picks if f"{p['match']}-{p['bet']}" not in sent_picks]

    if not new_main and not new_stats:
        print("No hay picks nuevos")
        return

    casa = "\U0001f7e2 STAKE" if len(new_main) > 5 else "\U0001f535 1XBET"
    msg = f"\U0001f3af <b>IVANPICKS - {title}</b>\n"
    msg += f"\U0001f4c5 {datetime.now(TZ).strftime('%d/%m/%Y %H:%M')}\n\n"

    if new_main:
        msg += f"\U0001f3e6 <b>Casa recomendada: {casa}</b>\n\n"
        for i, p in enumerate(new_main, 1):
            msg += f"<b>Pick {i}</b>\n"
            msg += f"\u26bd {p['match']}\n"
            msg += f"\U0001f3c6 {p['league']}\n"
            msg += f"\u2705 Apuesta: {p['bet']}\n"
            msg += f"\U0001f4b0 Cuota: {p['odd']}\n"
            msg += f"\U0001f4ca Probabilidad: {p['prob']}%\n\n"

    if new_stats:
        msg += f"\U0001f4ca <b>ANALISIS ESTADISTICO</b>\n"
        msg += f"<i>Busca estas cuotas en tu casa de apuestas</i>\n\n"
        for p in new_stats:
            msg += f"\u26bd {p['match']}\n"
            msg += f"\U0001f3c6 {p['league']}\n"
            msg += f"\U0001f4cc {p['bet']}\n"
            msg += f"\U0001f4ca Probabilidad: {p['prob']}%\n"
            msg += f"\U0001f4c8 Promedio H2H: {p['avg']}\n\n"

    msg += "\u26a0\ufe0f Aposta con responsabilidad."
    send_telegram(msg)

    for p in new_main + new_stats:
        sent_picks.add(f"{p['match']}-{p['bet']}")

def daily_analysis():
    print("Analisis diario 00:00...")
    sent_picks.clear()
    cache.clear()
    main_picks, stats_picks = get_todays_picks()
    send_picks(main_picks, stats_picks, "Picks del dia")

def check_new_opportunities():
    print("Revisando nuevas oportunidades...")
    main_picks, stats_picks = get_todays_picks()
    new_main = [p for p in main_picks if f"{p['match']}-{p['bet']}" not in sent_picks]
    new_stats = [p for p in stats_picks if f"{p['match']}-{p['bet']}" not in sent_picks]
    if new_main or new_stats:
        send_picks(new_main[:3], new_stats[:2], "Nueva oportunidad!")

print("Bot IvanPicks iniciando...")
send_telegram("\U0001f916 Bot IvanPicks iniciado y activo!")
daily_analysis()

schedule.every().day.at("03:00").do(daily_analysis)
schedule.every(2).hours.do(check_new_opportunities)

while True:
    schedule.run_pending()
    time.sleep(60)
