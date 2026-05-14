import os
import requests
from datetime import datetime
import pytz
import time
import schedule
import json

TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ODDS_API_KEY = os.environ.get("ODDS_API_KEY")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")

TZ = pytz.timezone("America/Argentina/Buenos_Aires")

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
REQUESTS_FILE = os.path.join(BASE_DIR, "api_requests.json")
SENT_PICKS_FILE = os.path.join(BASE_DIR, "sent_picks.json")

SOUTH_AMERICAN_LEAGUES = {
    "soccer_argentina_primera_division",
    "soccer_brazil_campeonato",
    "soccer_mexico_ligamx",
    "soccer_chile_campeonato",
    "soccer_colombia_primera_a",
    "soccer_uruguay_primera_division",
    "soccer_conmebol_copa_libertadores",
    "soccer_usa_mls",
    "soccer_japan_j_league",
    "soccer_saudi_arabias_league",
}

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

cache = {}

def get_current_season(sport_key=None):
    now = datetime.now(TZ)
    if sport_key and sport_key in SOUTH_AMERICAN_LEAGUES:
        return now.year
    return now.year if now.month >= 7 else now.year - 1

def load_request_count():
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    try:
        with open(REQUESTS_FILE, "r") as f:
            data = json.load(f)
            if data.get("date") == today:
                return data.get("count", 0)
    except:
        pass
    return 0

def save_request_count(count):
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    try:
        with open(REQUESTS_FILE, "w") as f:
            json.dump({"date": today, "count": count}, f)
    except:
        pass

def get_request_count():
    return load_request_count()

def increment_request_count():
    count = load_request_count() + 1
    save_request_count(count)
    return count

def load_sent_picks():
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    try:
        with open(SENT_PICKS_FILE, "r") as f:
            data = json.load(f)
            if data.get("date") == today:
                return set(data.get("picks", []))
    except:
        pass
    return set()

def save_sent_picks(picks_set):
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    try:
        with open(SENT_PICKS_FILE, "w") as f:
            json.dump({"date": today, "picks": list(picks_set)}, f)
    except:
        pass

sent_picks = load_sent_picks()

def send_telegram(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    if len(message) > 4000:
        parts = [message[i:i+4000] for i in range(0, len(message), 4000)]
        for part in parts:
            requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": part, "parse_mode": "HTML"}, timeout=10)
            time.sleep(1)
        return
    r = requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}, timeout=10)
    print(f"Telegram: {r.status_code}")

def api_football_get(endpoint, params):
    count = get_request_count()
    if count >= 90:
        print(f"Limite requests alcanzado ({count}/100)")
        return []

    cache_key = f"{endpoint}_{json.dumps(params, sort_keys=True)}"
    if cache_key in cache:
        return cache[cache_key]

    try:
        url = f"https://v3.football.api-sports.io/{endpoint}"
        headers = {"x-apisports-key": API_FOOTBALL_KEY}
        r = requests.get(url, headers=headers, params=params)
        new_count = increment_request_count()
        print(f"API-Football #{new_count}: {endpoint} {params}")
        data = r.json().get("response", [])
        cache[cache_key] = data
        return data
    except Exception as e:
        print(f"API-Football error: {e}")
        return []

def get_team_id(team_name, league_id, sport_key=None):
    season = get_current_season(sport_key)
    data = api_football_get("teams", {"name": team_name, "league": league_id, "season": season})
    return data[0]["team"]["id"] if data else None

def get_team_form(team_id, sport_key=None):
    season = get_current_season(sport_key)
    fixtures = api_football_get("fixtures", {
        "team": team_id, "last": 8,
        "season": season, "status": "FT"
    })
    if not fixtures:
        return None

    wins = 0
    goals_for = []
    goals_against = []

    for f in fixtures:
        hid = f["teams"]["home"]["id"]
        aid = f["teams"]["away"]["id"]
        hg = f["goals"]["home"] or 0
        ag = f["goals"]["away"] or 0
        if hid == team_id:
            goals_for.append(hg)
            goals_against.append(ag)
            if f["teams"]["home"]["winner"]:
                wins += 1
        elif aid == team_id:
            goals_for.append(ag)
            goals_against.append(hg)
            if f["teams"]["away"]["winner"]:
                wins += 1

    if not goals_for:
        return None

    return {
        "win_rate": round(wins / len(fixtures) * 100),
        "avg_for": round(sum(goals_for) / len(goals_for), 1),
        "avg_against": round(sum(goals_against) / len(goals_against), 1),
        "sample": len(fixtures)
    }

def get_goals_and_form(home, away, league_id, sport_key=None):
    home_id = get_team_id(home, league_id, sport_key)
    away_id = get_team_id(away, league_id, sport_key)

    home_form = get_team_form(home_id, sport_key) if home_id else None
    away_form = get_team_form(away_id, sport_key) if away_id else None

    h2h = []
    if home_id and away_id:
        h2h = api_football_get("fixtures/headtohead", {
            "h2h": f"{home_id}-{away_id}", "last": 8, "status": "FT"
        })

    if len(h2h) >= 4:
        goals_list = []
        btts = 0
        for g in h2h:
            hg = g["goals"]["home"] or 0
            ag = g["goals"]["away"] or 0
            goals_list.append(hg + ag)
            if hg > 0 and ag > 0:
                btts += 1
        avg = sum(goals_list) / len(goals_list)
        return {
            "avg_goals": round(avg, 1),
            "over25_prob": int(sum(1 for g in goals_list if g > 2.5) / len(goals_list) * 100),
            "over15_prob": int(sum(1 for g in goals_list if g > 1.5) / len(goals_list) * 100),
            "btts_prob": int(btts / len(h2h) * 100),
            "home_form": home_form["win_rate"] if home_form else None,
            "away_form": away_form["win_rate"] if away_form else None,
            "sample": len(h2h)
        }

    if home_form and away_form:
        avg = round((home_form["avg_for"] + away_form["avg_for"]), 1)
        return {
            "avg_goals": avg,
            "over25_prob": int(min(avg / 3.0 * 70, 80)),
            "over15_prob": int(min(avg / 2.0 * 70, 85)),
            "btts_prob": 60 if home_form["avg_for"] > 0.8 and away_form["avg_for"] > 0.8 else 38,
            "home_form": home_form["win_rate"],
            "away_form": away_form["win_rate"],
            "sample": min(home_form["sample"], away_form["sample"])
        }

    return None

def analyze_corners_cards(home, away, league_id, sport_key=None):
    if get_request_count() >= 50:
        return None

    home_id = get_team_id(home, league_id, sport_key)
    away_id = get_team_id(away, league_id, sport_key)
    if not home_id or not away_id:
        return None

    season = get_current_season(sport_key)
    fixture_corners = {}
    fixture_cards = {}

    for team_id, side in [(home_id, "home"), (away_id, "away")]:
        fixtures = api_football_get("fixtures", {
            "team": team_id, "last": 6,
            "season": season, "status": "FT"
        })
        if not fixtures:
            continue
        count = 0
        for f in fixtures:
            if count >= 3:
                break
            if get_request_count() >= 55:
                break
            fid = f["fixture"]["id"]
            stats = api_football_get("fixtures/statistics", {"fixture": fid})
            for ts in stats:
                if ts.get("team", {}).get("id") == team_id:
                    for s in ts.get("statistics", []):
                        val = s.get("value")
                        if val is None:
                            continue
                        try:
                            if s["type"] == "Corner Kicks":
                                if fid not in fixture_corners:
                                    fixture_corners[fid] = {}
                                fixture_corners[fid][side] = int(val)
                            elif s["type"] == "Yellow Cards":
                                if fid not in fixture_cards:
                                    fixture_cards[fid] = {}
                                fixture_cards[fid][side] = int(val)
                        except:
                            pass
            count += 1

    all_corners = []
    for fid, sides in fixture_corners.items():
        if "home" in sides and "away" in sides:
            all_corners.append(sides["home"] + sides["away"])

    all_cards = []
    for fid, sides in fixture_cards.items():
        if "home" in sides and "away" in sides:
            all_cards.append(sides["home"] + sides["away"])

    if len(all_corners) < 4 or len(all_cards) < 4:
        print(f"Datos insuficientes {home} vs {away}: corners={len(all_corners)}, cards={len(all_cards)}")
        return None

    avg_c = round(sum(all_corners) / len(all_corners), 1)
    avg_k = round(sum(all_cards) / len(all_cards), 1)
    n = len(all_corners)

    return {
        "corners_avg": avg_c,
        "cards_avg": avg_k,
        "corners_over95_prob": int(sum(1 for c in all_corners if c > 9.5) / n * 100),
        "corners_over105_prob": int(sum(1 for c in all_corners if c > 10.5) / n * 100),
        "cards_over35_prob": int(sum(1 for k in all_cards if k > 3.5) / n * 100),
        "cards_over45_prob": int(sum(1 for k in all_cards if k > 4.5) / n * 100),
        "sample": n
    }

def get_best_market(home, away, bookmakers, stats):
    if not stats:
        return None
    candidates = []
    for bm in bookmakers:
        for market in bm.get("markets", []):
            key = market["key"]
            for outcome in market["outcomes"]:
                odd = float(outcome["price"])
                name = outcome["name"]
                implied = round(1 / odd * 100, 1)
                stat_prob = None
                label = name

                if key == "h2h":
                    if name == home and stats["home_form"] is not None:
                        stat_prob = stats["home_form"]
                        label = f"Gana {home}"
                    elif name == away and stats["away_form"] is not None:
                        stat_prob = stats["away_form"]
                        label = f"Gana {away}"
                elif key == "totals":
                    if "Over" in name and "2.5" in name:
                        stat_prob = stats["over25_prob"]
                        label = "Mas de 2.5 goles"
                    elif "Under" in name and "2.5" in name:
                        stat_prob = 100 - stats["over25_prob"]
                        label = "Menos de 2.5 goles"
                    elif "Over" in name and "1.5" in name:
                        stat_prob = stats["over15_prob"]
                        label = "Mas de 1.5 goles"
                elif key == "btts":
                    if name == "Yes":
                        stat_prob = stats["btts_prob"]
                        label = "Ambos equipos marcan"
                    else:
                        stat_prob = 100 - stats["btts_prob"]
                        label = "No ambos marcan"

                if stat_prob is None:
                    continue
                value = stat_prob - implied
                if 1.35 <= odd <= 2.50 and stat_prob >= 55 and value >= 0:
                    candidates.append({"bet": label, "odd": odd, "prob": stat_prob, "value": round(value, 1)})

    candidates.sort(key=lambda x: (x["prob"], x["value"]), reverse=True)
    return candidates[0] if candidates else None

def is_useful_hour():
    hour = datetime.now(TZ).hour
    return 8 <= hour <= 23

def get_todays_picks():
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    print(f"Analizando: {today} | Requests usados: {get_request_count()}/100")

    main_picks = []
    stats_picks = []
    matches_analyzed = 0

    for sport_key, (flag, league_name, league_id) in LEAGUE_INFO.items():
        if get_request_count() >= 85:
            print("Limite requests alcanzado")
            break
        try:
            url = f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds"
            params = {"apiKey": ODDS_API_KEY, "regions": "eu", "markets": "h2h,totals,btts", "oddsFormat": "decimal"}
            r = requests.get(url, params=params)

            # DEBUG TEMPORAL: ver que devuelve la Odds API
            print(f"[{sport_key}] HTTP {r.status_code} | juegos={len(r.json()) if r.status_code == 200 else 'ERROR: ' + r.text[:100]}")
            if r.status_code == 200 and r.json():
                ejemplo = r.json()[0]
                print(f"  commence_time ejemplo: {ejemplo.get('commence_time')} | today buscado: {today}")
            # FIN DEBUG

            if r.status_code != 200:
                continue

            league_count = 0
            for game in r.json():
                if today not in game.get("commence_time", ""):
                    continue
                if league_count >= 3:
                    break
                if get_request_count() >= 85:
                    break

                home = game["home_team"]
                away = game["away_team"]
                bookmakers = game.get("bookmakers", [])
                if not bookmakers:
                    continue

                stats = get_goals_and_form(home, away, league_id, sport_key)
                best = get_best_market(home, away, bookmakers, stats)
                if best:
                    main_picks.append({
                        "match": f"{home} vs {away}",
                        "league": f"{flag} {league_name}",
                        "bet": best["bet"],
                        "odd": best["odd"],
                        "prob": best["prob"],
                    })

                if get_request_count() < 50:
                    cc = analyze_corners_cards(home, away, league_id, sport_key)
                    if cc:
                        if cc["corners_over95_prob"] >= 65:
                            stats_picks.append({
                                "match": f"{home} vs {away}",
                                "league": f"{flag} {league_name}",
                                "bet": "Mas de 9.5 corners",
                                "prob": cc["corners_over95_prob"],
                                "avg": cc["corners_avg"],
                                "sample": cc["sample"]
                            })
                        if cc["cards_over35_prob"] >= 65:
                            stats_picks.append({
                                "match": f"{home} vs {away}",
                                "league": f"{flag} {league_name}",
                                "bet": "Mas de 3.5 tarjetas",
                                "prob": cc["cards_over35_prob"],
                                "avg": cc["cards_avg"],
                                "sample": cc["sample"]
                            })

                league_count += 1
                matches_analyzed += 1

        except Exception as e:
            print(f"Error {sport_key}: {e}")

    print(f"Partidos analizados: {matches_analyzed} | Requests totales: {get_request_count()}/100")

    main_picks.sort(key=lambda x: x["prob"], reverse=True)
    stats_picks.sort(key=lambda x: x["prob"], reverse=True)

    seen = set()
    unique_main = []
    unique_stats = []
    for p in main_picks:
        k = f"{p['match']}-{p['bet']}"
        if k not in seen:
            seen.add(k)
            unique_main.append(p)
    for p in stats_picks:
        k = f"{p['match']}-{p['bet']}"
        if k not in seen:
            seen.add(k)
            unique_stats.append(p)

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
        msg += f"\U0001f3e6 <b>Casa: {casa}</b>\n\n"
        for i, p in enumerate(new_main, 1):
            msg += f"<b>Pick {i}</b>\n"
            msg += f"\u26bd {p['match']}\n"
            msg += f"\U0001f3c6 {p['league']}\n"
            msg += f"\u2705 Apuesta: {p['bet']}\n"
            msg += f"\U0001f4b0 Cuota: {p['odd']}\n"
            msg += f"\U0001f4ca Prob: {p['prob']}%\n\n"

    if new_stats:
        msg += f"\U0001f4ca <b>ANALISIS ESTADISTICO</b>\n"
        msg += f"<i>Busca estas cuotas en tu casa de apuestas</i>\n\n"
        for p in new_stats:
            msg += f"\u26bd {p['match']}\n"
            msg += f"\U0001f3c6 {p['league']}\n"
            msg += f"\U0001f4cc {p['bet']}\n"
            msg += f"\U0001f4ca Prob: {p['prob']}% | Prom: {p['avg']} | Muestra: {p['sample']} partidos\n\n"

    msg += "\u26a0\ufe0f Aposta con responsabilidad."
    send_telegram(msg)

    for p in new_main + new_stats:
        sent_picks.add(f"{p['match']}-{p['bet']}")
    save_sent_picks(sent_picks)

def daily_analysis():
    print("Analisis diario 00:00...")
    sent_picks.clear()
    save_sent_picks(sent_picks)
    cache.clear()
    save_request_count(0)
    main_picks, stats_picks = get_todays_picks()
    send_picks(main_picks, stats_picks, "Picks del dia")

def check_new_opportunities():
    if not is_useful_hour():
        print("Fuera de horario util, saltando revision")
        return
    if get_request_count() >= 85:
        print("Sin requests disponibles")
        return
    print("Revisando nuevas oportunidades...")
    main_picks, stats_picks = get_todays_picks()
    new_main = [p for p in main_picks if f"{p['match']}-{p['bet']}" not in sent_picks]
    new_stats = [p for p in stats_picks if f"{p['match']}-{p['bet']}" not in sent_picks]
    if new_main or new_stats:
        send_picks(new_main[:3], new_stats[:2], "Nueva oportunidad!")

print("Bot IvanPicks iniciando...")
send_telegram("\U0001f916 Bot IvanPicks iniciado y activo!")

if not sent_picks:
    daily_analysis()
else:
    print("Picks del dia ya enviados previamente, saltando analisis inicial")

schedule.every().day.at("03:00").do(daily_analysis)
schedule.every(2).hours.do(check_new_opportunities)

while True:
    schedule.run_pending()
    time.sleep(60)