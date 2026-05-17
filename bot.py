import os, requests, time, schedule, json, math
from datetime import datetime
from io import StringIO
import pytz, pandas as pd
from scipy.stats import poisson

TELEGRAM_TOKEN   = os.environ.get("TELEGRAM_TOKEN")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID")
ODDS_API_KEY     = os.environ.get("ODDS_API_KEY")
API_FOOTBALL_KEY = os.environ.get("API_FOOTBALL_KEY")

TZ            = pytz.timezone("America/Argentina/Buenos_Aires")
REQUESTS_FILE = "/tmp/api_requests.json"
MIN_PROB      = 60
MIN_SAMPLE    = 5
MAX_API_REQ   = 90
CORNER_LINES  = [7.5, 8.5, 9.5, 10.5, 11.5]
CARD_LINES    = [1.5, 2.5, 3.5, 4.5]

LEAGUE_INFO = {
    "soccer_epl":                        ("🏴󠁧󠁢󠁥󠁮󠁧󠁿 Premier League",   39),
    "soccer_spain_la_liga":              ("🇪🇸 La Liga",          140),
    "soccer_italy_serie_a":              ("🇮🇹 Serie A",          135),
    "soccer_uefa_champs_league":         ("🏆 Champions League",   2),
    "soccer_argentina_primera_division": ("🇦🇷 Liga Argentina",   128),
    "soccer_germany_bundesliga":         ("🇩🇪 Bundesliga",        78),
    "soccer_france_ligue_one":           ("🇫🇷 Ligue 1",           61),
}

SENT_PICKS_FILE = "/tmp/sent_picks.json"
REFEREE_FILE = "/tmp/referee_history.json"
api_cache = {}

def get_current_season():
    now = datetime.now(TZ)
    return now.year if now.month >= 7 else now.year - 1

def is_useful_hour():
    return 1 <= datetime.now(TZ).hour <= 23

def load_req():
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    try:
        with open(REQUESTS_FILE) as f:
            d = json.load(f)
            return d.get("count", 0) if d.get("date") == today else 0
    except:
        return 0

def save_req(n):
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    try:
        with open(REQUESTS_FILE, "w") as f:
            json.dump({"date": today, "count": n}, f)
    except:
        pass

def inc_req():
    n = load_req() + 1
    save_req(n)
    return n

def load_sent_picks():
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    try:
        with open(SENT_PICKS_FILE) as f:
            d = json.load(f)
            return set(d.get("picks", [])) if d.get("date") == today else set()
    except:
        return set()

def save_sent_picks(picks_set):
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    try:
        with open(SENT_PICKS_FILE, "w") as f:
            json.dump({"date": today, "picks": list(picks_set)}, f)
    except:
        pass
def load_referee_history():
    try:
        with open(REFEREE_FILE) as f:
            return json.load(f)
    except:
        return {}

def save_referee_history(data):
    try:
        with open(REFEREE_FILE, "w") as f:
            json.dump(data, f)
    except:
        pass

def update_referee(name, yellows, reds):
    if not name:
        return
    data = load_referee_history()
    if name not in data:
        data[name] = {"matches": [], "total_yellows": 0, "total_reds": 0, "count": 0}
    data[name]["matches"].append({"yellows": yellows, "reds": reds})
    data[name]["total_yellows"] += yellows
    data[name]["total_reds"] += reds
    data[name]["count"] += 1
    save_referee_history(data)

def get_referee_stats(name):
    if not name:
        return None
    data = load_referee_history()
    if name not in data or data[name]["count"] < 3:
        return None
    d = data[name]
    return {
        "name": name,
        "avg_yellows": round(d["total_yellows"] / d["count"], 1),
        "avg_reds":    round(d["total_reds"] / d["count"], 1),
        "matches":     d["count"],
    }
def send_telegram(msg):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    for part in [msg[i:i+4000] for i in range(0, len(msg), 4000)]:
        requests.post(url, json={"chat_id": TELEGRAM_CHAT_ID, "text": part, "parse_mode": "HTML"})
        time.sleep(1)

def find_best_line(values, lines, label):
    if len(values) < MIN_SAMPLE:
        return None
    n = len(values)
    best, best_prob = None, 0
    for line in lines:
        over_prob  = int(sum(1 for v in values if v > line) / n * 100)
        under_prob = int(sum(1 for v in values if v < line) / n * 100)
        if over_prob >= MIN_PROB and under_prob >= MIN_PROB:
            prob = max(over_prob, under_prob)
            bet  = f"Mas de {line} {label}" if over_prob >= under_prob else f"Menos de {line} {label}"
            if prob > best_prob:
                best_prob, best = prob, {"bet": bet, "prob": prob}
            continue
        for prob, bet in [
            (over_prob,  f"Mas de {line} {label}"),
            (under_prob, f"Menos de {line} {label}"),
        ]:
            if prob >= MIN_PROB and prob > best_prob:
                best_prob, best = prob, {"bet": bet, "prob": prob}
    return best
def apif(endpoint, params):
    if load_req() >= MAX_API_REQ:
        return []
    key = f"{endpoint}|{sorted(params.items())}"
    if key in api_cache:
        return api_cache[key]
    try:
        r = requests.get(f"https://v3.football.api-sports.io/{endpoint}",
            headers={"x-apisports-key": API_FOOTBALL_KEY}, params=params, timeout=10)
        n = inc_req()
        print(f"[APIF #{n}] {endpoint}")
        data = r.json().get("response", [])
        api_cache[key] = data
        return data
    except Exception as e:
        print(f"[APIF ERROR] {e}")
        return []

def team_id(name, league_id):
    data = apif("teams", {"name": name, "league": league_id, "season": get_current_season()})
    return data[0]["team"]["id"] if data else None

def normalize(name):
    return name.lower().strip()

def team_id_fuzzy(name, league_id):
    tid = team_id(name, league_id)
    if tid:
        return tid
    data = apif("teams", {"league": league_id, "season": get_current_season()})
    name_n = normalize(name)
    for t in data:
        tname = normalize(t["team"]["name"])
        if name_n in tname or tname in name_n:
            return t["team"]["id"]
        words = [w for w in name_n.split() if len(w) >= 4]
        if any(w in tname for w in words):
            return t["team"]["id"]
    return None

def team_form(tid):
    fx = apif("fixtures", {"team": tid, "last": 8, "season": get_current_season(), "status": "FT"})
    if not fx:
        return None
    wins, gf, ga = 0, [], []
    for f in fx:
        hid = f["teams"]["home"]["id"]
        hg, ag = f["goals"]["home"] or 0, f["goals"]["away"] or 0
        is_home = hid == tid
        gf.append(hg if is_home else ag)
        ga.append(ag if is_home else hg)
        if f["teams"]["home" if is_home else "away"]["winner"]:
            wins += 1
    n = len(fx)
    return {
        "win_rate":      round(wins / n * 100),
        "avg_for":       round(sum(gf) / n, 2),
        "avg_against":   round(sum(ga) / n, 2),
        "goals_list":    gf,
        "conceded_list": ga,
        "sample":        n,
    }
    
def fixture_corners_cards(tid, n=8):
    if load_req() >= 80:
        return [], [], []
    fx = apif("fixtures", {"team": tid, "last": n, "season": get_current_season(), "status": "FT"})
    corners, cards, totals = [], [], []
    for f in fx[:8]:
        if load_req() >= 85:
            break
        home_corners, away_corners = None, None
        home_cards, away_cards = None, None
        tid_is_home = f["teams"]["home"]["id"] == tid
        for ts in apif("fixtures/statistics", {"fixture": f["fixture"]["id"]}):
            is_home_team = ts.get("team", {}).get("id") == f["teams"]["home"]["id"]
            for s in ts.get("statistics", []):
                val = s.get("value")
                if val is None:
                    continue
                try:
                    v = int(val)
                    if s["type"] == "Corner Kicks":
                        if is_home_team:
                            home_corners = v
                        else:
                            away_corners = v
                    elif s["type"] == "Yellow Cards":
                        if is_home_team:
                            home_cards = v
                        else:
                            away_cards = v
                except:
                    pass
        if home_corners is not None and away_corners is not None:
            total_c = home_corners + away_corners
            totals.append(total_c)
            corners.append(home_corners if tid_is_home else away_corners)
        if home_cards is not None and away_cards is not None:
            cards.append(home_cards if tid_is_home else away_cards)
    return corners, cards, totals
def poisson_prob_over(lam, threshold):
    if lam <= 0:
        return 0
    k = math.floor(threshold)
    prob_under_eq = sum(poisson.pmf(i, lam) for i in range(0, k + 1))
    return max(0, min(int((1 - prob_under_eq) * 100), 95))

def poisson_prob_under(lam, threshold):
    if lam <= 0:
        return 95
    k = math.floor(threshold)
    prob_under = sum(poisson.pmf(i, lam) for i in range(0, k + 1))
    return max(0, min(int(prob_under * 100), 95))

def analyze_goals(home, away, league_id):
    hid = team_id_fuzzy(home, league_id)
    aid = team_id_fuzzy(away, league_id)

    h2h = []
    if hid and aid:
        h2h = apif("fixtures/headtohead", {"h2h": f"{hid}-{aid}", "last": 8, "status": "FT"})

    if len(h2h) >= 4:
        goals, btts, hg_list, ag_list = [], [], [], []
        for g in h2h:
            hg  = g["goals"]["home"] or 0
            ag  = g["goals"]["away"] or 0
            goals.append(hg + ag)
            btts.append(1 if hg > 0 and ag > 0 else 0)
            if g["teams"]["home"]["id"] == hid:
                hg_list.append(hg); ag_list.append(ag)
            else:
                hg_list.append(ag); ag_list.append(hg)
        n = len(h2h)
        over25  = int(sum(1 for g in goals if g > 2.5) / n * 100)
        under25 = int(sum(1 for g in goals if g < 2.5) / n * 100)
        over15  = int(sum(1 for g in goals if g > 1.5) / n * 100)
        return {
            "over25_prob":    over25,
            "under25_prob":   under25,
            "over15_prob":    over15,
            "btts_prob":      int(sum(btts) / n * 100),
            "home_goals":     hg_list,
            "away_goals":     ag_list,
            "avg_goals":      round(sum(goals) / n, 1),
            "sample":         n,
            "source":         "h2h",
        }

    hf = team_form(hid) if hid else None
    af = team_form(aid) if aid else None

    if not hf or not af:
        return None

    lam_home  = (hf["avg_for"] + af["avg_against"]) / 2
    lam_away  = (af["avg_for"] + hf["avg_against"]) / 2
    lam_total = lam_home + lam_away

    p_home_scores = int((1 - poisson.pmf(0, lam_home)) * 100)
    p_away_scores = int((1 - poisson.pmf(0, lam_away)) * 100)

    return {
        "over25_prob":    poisson_prob_over(lam_total, 2.5),
        "under25_prob":   poisson_prob_under(lam_total, 2.5),
        "over15_prob":    poisson_prob_over(lam_total, 1.5),
        "btts_prob":      int(p_home_scores * p_away_scores / 100),
        "home_goals":     hf.get("goals_list", []),
        "away_goals":     af.get("goals_list", []),
        "home_form":      hf["win_rate"],
        "away_form":      af["win_rate"],
        "avg_goals":      round(lam_total, 1),
        "sample":         min(hf["sample"], af["sample"]),
        "source":         "form",
    }

def analyze_cc(home, away, league_id):
    res = {k: None for k in [
        "corners_total", "corners_home", "corners_away",
        "cards_total",   "cards_home",   "cards_away",
        "corners_avg",   "cards_avg",    "source",
    ]}
    res["source"] = "none"

    hid = team_id_fuzzy(home, league_id)
    aid = team_id_fuzzy(away, league_id)

    if not hid or not aid or load_req() >= 80:
        return res

    hc_list, hk_list, h_totals = fixture_corners_cards(hid, n=8)
    ac_list, ak_list, a_totals = fixture_corners_cards(aid, n=8)

    if len(hc_list) >= MIN_SAMPLE and len(ac_list) >= MIN_SAMPLE:
        avg_c_home = sum(hc_list) / len(hc_list)
        avg_c_away = sum(ac_list) / len(ac_list)
        avg_total  = avg_c_home + avg_c_away
        total_list = h_totals if len(h_totals) >= MIN_SAMPLE else \
                     [avg_c_home + avg_c_away] * max(len(hc_list), len(ac_list))
        res["corners_total"] = find_best_line(total_list, CORNER_LINES, "corners")
        res["corners_home"]  = find_best_line(hc_list, [3.5, 4.5, 5.5, 6.5], f"corners ({home})")
        res["corners_away"]  = find_best_line(ac_list, [3.5, 4.5, 5.5, 6.5], f"corners ({away})")
        res["corners_avg"]   = round(avg_total, 1)
        res["source"]        = "api_football"

    if len(hk_list) >= MIN_SAMPLE and len(ak_list) >= MIN_SAMPLE:
        avg_k_home = sum(hk_list) / len(hk_list)
        avg_k_away = sum(ak_list) / len(ak_list)
        res["cards_total"] = find_best_line(hk_list + ak_list, CARD_LINES, "tarjetas")
        res["cards_home"]  = find_best_line(hk_list, [0.5, 1.5, 2.5], f"tarjetas ({home})")
        res["cards_away"]  = find_best_line(ak_list, [0.5, 1.5, 2.5], f"tarjetas ({away})")
        res["cards_avg"]   = round(avg_k_home + avg_k_away, 1)
        res["source"]      = "api_football"

    return res
def best_odds_pick(home, away, bookmakers, stats):
    if not stats:
        return None
    candidates = []
    MAP = {
        ("h2h",    home):        ("home_form",   f"Gana {home}"),
        ("h2h",    away):        ("away_form",   f"Gana {away}"),
        ("totals", "Over 2.5"):  ("over25_prob", "Mas de 2.5 goles"),
        ("totals", "Under 2.5"): ("under25_prob","Menos de 2.5 goles"),
        ("totals", "Over 1.5"):  ("over15_prob", "Mas de 1.5 goles"),
        ("btts",   "Yes"):       ("btts_prob",   "Ambos equipos marcan"),
        ("btts",   "No"):        (None,          "No ambos marcan"),
    }
    for bm in bookmakers:
        for market in bm.get("markets", []):
            mk = market["key"]
            for outcome in market["outcomes"]:
                name, odd = outcome["name"], float(outcome["price"])
                implied = round(1 / odd * 100, 1)
                sp, label = None, name
                for (k, n), (sk, lbl) in MAP.items():
                    if mk == k and (normalize(n) in normalize(name) or normalize(name) in normalize(n)):
                        btts_prob = stats.get("btts_prob")
                        if sk is None:
                            sp = 100 - btts_prob if btts_prob is not None else None
                        else:
                            sp = stats.get(sk)
                        label = lbl
                        break
                if sp is None:
                    continue
                value = sp - implied
                if 1.30 <= odd <= 2.60 and sp >= 55 and value >= 2:
                    candidates.append({"bet": label, "odd": odd, "prob": sp, "value": round(value, 1)})
    candidates.sort(key=lambda x: (x["value"], x["prob"]), reverse=True)
    return candidates[0] if candidates else None

def get_todays_picks():
    today = datetime.now(TZ).strftime("%Y-%m-%d")
    print(f"\n{'='*50}\nAnalisis: {today} | APIF: {load_req()}/100\n{'='*50}")
    odds_picks, stats_picks = [], []
    analyzed = 0

    for sport_key, (league_name, league_id) in LEAGUE_INFO.items():
        if load_req() >= MAX_API_REQ:
            break
        try:
            r = requests.get(
                f"https://api.the-odds-api.com/v4/sports/{sport_key}/odds",
                params={"apiKey": ODDS_API_KEY, "regions": "eu",
                        "markets": "h2h,totals", "oddsFormat": "decimal"},
                timeout=10,
            )
            if r.status_code != 200:
                print(f"[ODDS ERROR] {league_name} HTTP {r.status_code}: {r.text[:100]}")
                continue
            league_count = 0
            for game in r.json():
                if today not in game.get("commence_time", ""):
                    continue
                if league_count >= 3 or load_req() >= MAX_API_REQ:
                    break
                home, away = game["home_team"], game["away_team"]
                bm = game.get("bookmakers", [])
                if not bm:
                    continue
                print(f"[{league_name}] {home} vs {away}")
                hid = team_id_fuzzy(home, league_id)
                aid = team_id_fuzzy(away, league_id)
                referee_name = None
                ref_stats = None
                if hid and aid:
                    fx_data = apif("fixtures", {"team": hid, "next": 1})
                    if fx_data:
                        referee_raw = fx_data[0].get("fixture", {}).get("referee") or ""
                        referee_name = referee_raw.split(",")[0].strip() if referee_raw else None
                        ref_stats = get_referee_stats(referee_name)


                stats = analyze_goals(home, away, league_id)
                pick  = best_odds_pick(home, away, bm, stats)
                if pick:
                    odds_picks.append({"match": f"{home} vs {away}", "league": league_name, "referee": ref_stats, **pick})

                if stats:
                    for goal_list, label in [
                        (stats.get("home_goals"), home),
                        (stats.get("away_goals"), away),
                    ]:
                        if goal_list and len(goal_list) >= MIN_SAMPLE:
                            p = find_best_line(goal_list, [0.5, 1.5], f"goles ({label})")
                            if p:
                                stats_picks.append({
                                    "match": f"{home} vs {away}", "league": league_name,
                                    "bet": p["bet"], "prob": p["prob"],
                                    "avg": stats["avg_goals"], "sample": stats["sample"],
                                })

                cc = analyze_cc(home, away, league_id)
                if ref_stats and cc.get("cards_avg") is not None:
                    ref_factor = ref_stats["avg_yellows"] / 3.5
                    cc["cards_avg"] = round((cc["cards_avg"] + ref_stats["avg_yellows"]) / 2, 1)
                    if cc.get("cards_total") and cc["cards_total"].get("prob"):
                        adj = min(10, int((ref_factor - 1) * 15))
                        cc["cards_total"]["prob"] = min(95, cc["cards_total"]["prob"] + adj)
                        cc["cards_total"]["bet"] = cc["cards_total"]["bet"] + f" (Árbitro: {ref_stats['name']} {ref_stats['avg_yellows']}AM/p)"

                for field in ["corners_total", "corners_home", "corners_away",
                              "cards_total",   "cards_home",   "cards_away"]:
                    p = cc.get(field)
                    if p:
                        avg = cc.get("corners_avg") if "corner" in field else cc.get("cards_avg")
                        stats_picks.append({
                            "match": f"{home} vs {away}", "league": league_name,
                            "bet": p["bet"], "prob": p["prob"], "avg": avg,
                            "sample": "ultimos partidos",
                        })

                league_count += 1
                analyzed += 1

        except Exception as e:
            print(f"[ERROR {sport_key}] {e}")

    print(f"[Resumen] Partidos: {analyzed} | APIF: {load_req()}/100")
    odds_picks.sort(key=lambda x: (x["value"], x["prob"]), reverse=True)
    stats_picks.sort(key=lambda x: x["prob"], reverse=True)

    seen = set()
    def dedup(lst):
        out = []
        for p in lst:
            k = f"{p['match']}-{p['bet']}"
            if k not in seen:
                seen.add(k)
                out.append(p)
        return out

    return dedup(odds_picks)[:10], dedup(stats_picks)[:8]

def send_picks(odds_picks, stats_picks, title="Picks del dia"):
    sent_picks = load_sent_picks()
    new_o = [p for p in odds_picks  if f"{p['match']}-{p['bet']}" not in sent_picks]
    new_s = [p for p in stats_picks if f"{p['match']}-{p['bet']}" not in sent_picks]
    if not new_o and not new_s:
        print("Sin picks nuevos")
        send_telegram(f"IvanPicks - {title}\nSin picks con valor hoy.")
        return

    casa = "STAKE" if len(new_o) >= 2 else "1XBET"
    msg  = f"IVANPICKS - {title}\n"
    msg += f"{datetime.now(TZ).strftime('%d/%m/%Y %H:%M')}\n\n"

    if new_o:
        msg += f"Casa: {casa}\n\n"
        for i, p in enumerate(new_o, 1):
            msg += f"Pick {i}\n{p['match']}\n{p['league']}\n{p['bet']}\nCuota: {p['odd']} | Prob: {p['prob']}% | Valor: +{p['value']}%\n"
            if p.get("referee"):
                msg += f"Árbitro: {p['referee']['name']} | AM/p: {p['referee']['avg_yellows']} | Rojas/p: {p['referee']['avg_reds']}\n"
            msg += "\n"

    if new_s:
        msg += "ANALISIS ESTADISTICO\nBusca estas lineas en tu casa de apuestas\n\n"
        for p in new_s:
            msg += f"{p['match']} | {p['league']}\n{p['bet']}\nProb: {p['prob']}%"
            if p.get("avg"):
                msg += f" | Prom: {p['avg']}"
            msg += f" | Muestra: {p['sample']}\n\n"

    msg += "Apostá con responsabilidad."
    send_telegram(msg)

    for p in new_o + new_s:
        sent_picks.add(f"{p['match']}-{p['bet']}")
    save_sent_picks(sent_picks)

def daily_analysis():
    print("\n[CRON 03:00] Analisis diario...")
    api_cache.clear()
    o, s = get_todays_picks()
    send_picks(o, s, "Picks del dia")

def check_new_opportunities():
    if not is_useful_hour() or load_req() >= MAX_API_REQ:
        return
    print("[CRON 13:00] Revisando...")
    api_cache.clear()
    o, s = get_todays_picks()
    sent_picks = load_sent_picks()
    no = [x for x in o if f"{x['match']}-{x['bet']}" not in sent_picks]
    ns = [x for x in s if f"{x['match']}-{x['bet']}" not in sent_picks]
    if no or ns:
        send_picks(no[:3], ns[:3], "Nueva oportunidad!")
    else:
        print("[CRON 13:00] Sin picks nuevos")

if __name__ == "__main__":
    print("Bot IvanPicks iniciando...")
    send_telegram("Bot IvanPicks iniciado - Fuentes: Odds API + API-Football")
    daily_analysis()
    schedule.every().day.at("03:00").do(daily_analysis)
    schedule.every().day.at("13:00").do(check_new_opportunities)
    while True:
        schedule.run_pending()
        time.sleep(60)