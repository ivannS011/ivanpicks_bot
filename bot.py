import os, requests, time, schedule, json
from datetime import datetime
from io import StringIO
import pytz, pandas as pd
from scipy.stats import poisson

TELEGRAM_TOKEN   = os.environ.get(“TELEGRAM_TOKEN”)
TELEGRAM_CHAT_ID = os.environ.get(“TELEGRAM_CHAT_ID”)
ODDS_API_KEY     = os.environ.get(“ODDS_API_KEY”)
API_FOOTBALL_KEY = os.environ.get(“API_FOOTBALL_KEY”)

TZ            = pytz.timezone(“America/Argentina/Buenos_Aires”)
REQUESTS_FILE = “/tmp/api_requests.json”
MIN_PROB      = 60
MIN_SAMPLE    = 5
MAX_API_REQ   = 90
FBREF_DELAY   = 4
CORNER_LINES  = [7.5, 8.5, 9.5, 10.5, 11.5]
CARD_LINES    = [1.5, 2.5, 3.5, 4.5]

LEAGUE_INFO = {
“soccer_epl”:                        (“🏴󠁧󠁢󠁥󠁮󠁧󠁿”, “Premier League”,   39,  “9”),
“soccer_spain_la_liga”:              (“🇪🇸”, “La Liga”,          140, “12”),
“soccer_germany_bundesliga”:         (“🇩🇪”, “Bundesliga”,        78, “20”),
“soccer_italy_serie_a”:              (“🇮🇹”, “Serie A”,          135, “11”),
“soccer_france_ligue_one”:           (“🇫🇷”, “Ligue 1”,           61, “13”),
“soccer_uefa_champs_league”:         (“⭐”,  “Champions League”,   2,  “8”),
“soccer_uefa_europa_league”:         (“🟠”,  “Europa League”,      3, “19”),
“soccer_portugal_primeira_liga”:     (“🇵🇹”, “Primeira Liga”,     94, “32”),
“soccer_netherlands_eredivisie”:     (“🇳🇱”, “Eredivisie”,        88, “23”),
“soccer_argentina_primera_division”: (“🇦🇷”, “Liga Argentina”,   128, None),
“soccer_brazil_campeonato”:          (“🇧🇷”, “Brasileirao”,       71, None),
“soccer_conmebol_copa_libertadores”: (“🌎”,  “Copa Libertadores”, 13, None),
}

# FIX #6: sent_picks se persiste en disco para sobrevivir reinicios

SENT_PICKS_FILE = “/tmp/sent_picks.json”

api_cache   = {}
fbref_cache = {}

FBREF_HEADERS = {
“User-Agent”: “Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/124.0.0.0 Safari/537.36”,
“Accept-Language”: “en-US,en;q=0.9”,
}

# ── Utilidades ────────────────────────────────────────────────────────────────

def get_current_season():
now = datetime.now(TZ)
return now.year if now.month >= 7 else now.year - 1

def is_useful_hour():
return 1 <= datetime.now(TZ).hour <= 23

def load_req():
today = datetime.now(TZ).strftime(”%Y-%m-%d”)
try:
with open(REQUESTS_FILE) as f:
d = json.load(f)
return d.get(“count”, 0) if d.get(“date”) == today else 0
except:
return 0

def save_req(n):
today = datetime.now(TZ).strftime(”%Y-%m-%d”)
try:
with open(REQUESTS_FILE, “w”) as f:
json.dump({“date”: today, “count”: n}, f)
except:
pass

def inc_req():
n = load_req() + 1
save_req(n)
return n

# FIX #6: sent_picks persistente en disco

def load_sent_picks():
today = datetime.now(TZ).strftime(”%Y-%m-%d”)
try:
with open(SENT_PICKS_FILE) as f:
d = json.load(f)
return set(d.get(“picks”, [])) if d.get(“date”) == today else set()
except:
return set()

def save_sent_picks(picks_set):
today = datetime.now(TZ).strftime(”%Y-%m-%d”)
try:
with open(SENT_PICKS_FILE, “w”) as f:
json.dump({“date”: today, “picks”: list(picks_set)}, f)
except:
pass

def send_telegram(msg):
url = f”https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage”
for part in [msg[i:i+4000] for i in range(0, len(msg), 4000)]:
requests.post(url, json={“chat_id”: TELEGRAM_CHAT_ID, “text”: part, “parse_mode”: “HTML”})
time.sleep(1)

def find_best_line(values, lines, label):
“””
Requiere lista real de valores históricos (no repetidos).
Evalúa Over/Under para cada línea y devuelve el mejor pick si cumple MIN_PROB.
“””
if len(values) < MIN_SAMPLE:
return None
n = len(values)
best, best_prob = None, 0
for line in lines:
for prob, bet in [
(int(sum(1 for v in values if v > line) / n * 100), f”Más de {line} {label}”),
(int(sum(1 for v in values if v < line) / n * 100), f”Menos de {line} {label}”),
]:
if prob >= MIN_PROB and prob > best_prob:
best_prob, best = prob, {“bet”: bet, “prob”: prob}
return best

# ── API-Football ──────────────────────────────────────────────────────────────

def apif(endpoint, params):
if load_req() >= MAX_API_REQ:
return []
key = f”{endpoint}|{sorted(params.items())}”
if key in api_cache:
return api_cache[key]
try:
r = requests.get(f”https://v3.football.api-sports.io/{endpoint}”,
headers={“x-apisports-key”: API_FOOTBALL_KEY}, params=params, timeout=10)
n = inc_req()
print(f”[APIF #{n}] {endpoint}”)
data = r.json().get(“response”, [])
api_cache[key] = data
return data
except Exception as e:
print(f”[APIF ERROR] {e}”)
return []

def team_id(name, league_id):
data = apif(“teams”, {“name”: name, “league”: league_id, “season”: get_current_season()})
return data[0][“team”][“id”] if data else None

def team_form(tid):
fx = apif(“fixtures”, {“team”: tid, “last”: 8, “season”: get_current_season(), “status”: “FT”})
if not fx:
return None
wins, gf, ga, htf = 0, [], [], []
for f in fx:
hid = f[“teams”][“home”][“id”]
hg, ag   = f[“goals”][“home”] or 0, f[“goals”][“away”] or 0
hht, aht = (
(f.get(“score”, {}).get(“halftime”, {}) or {}).get(“home”) or 0,
(f.get(“score”, {}).get(“halftime”, {}) or {}).get(“away”) or 0,
)
is_home = hid == tid
gf.append(hg if is_home else ag)
ga.append(ag if is_home else hg)
htf.append(hht if is_home else aht)
if f[“teams”][“home” if is_home else “away”][“winner”]:
wins += 1
n = len(fx)
return {
“win_rate”:    round(wins / n * 100),
“avg_for”:     round(sum(gf) / n, 2),
“avg_against”: round(sum(ga) / n, 2),
“avg_ht_for”:  round(sum(htf) / n, 2),
“goals_list”:  gf,
“conceded_list”: ga,
“sample”:      n,
}

def fixture_corners_cards(tid, n=8):
“””
FIX: aumentado a 8 partidos para garantizar MIN_SAMPLE=5 con datos reales.
Devuelve listas reales de corners y tarjetas por partido.
“””
if load_req() >= 80:
return [], []
fx = apif(“fixtures”, {“team”: tid, “last”: n, “season”: get_current_season(), “status”: “FT”})
corners, cards = [], []
for f in fx[:8]:
if load_req() >= 85:
break
for ts in apif(“fixtures/statistics”, {“fixture”: f[“fixture”][“id”]}):
if ts.get(“team”, {}).get(“id”) != tid:
continue
for s in ts.get(“statistics”, []):
val = s.get(“value”)
if val is None:
continue
try:
v = int(val)
if s[“type”] == “Corner Kicks”:
corners.append(v)
elif s[“type”] == “Yellow Cards”:
cards.append(v)
except:
pass
return corners, cards

# ── FBRef ─────────────────────────────────────────────────────────────────────

def fbref_table(url, col):
try:
time.sleep(FBREF_DELAY + 1.0)
r = requests.get(url, headers=FBREF_HEADERS, timeout=20)
# FIX #3: manejo explícito de bloqueo por FBRef
if r.status_code == 429:
print(f”[FBRef] Rate limited (429), esperando 60s…”)
time.sleep(60)
r = requests.get(url, headers=FBREF_HEADERS, timeout=20)
if r.status_code != 200:
print(f”[FBRef] HTTP {r.status_code} en {url}”)
return {}
html = r.text.replace(”<!--", "").replace("-->”, “”)
for df in pd.read_html(StringIO(html)):
if isinstance(df.columns, pd.MultiIndex):
df.columns = [” “.join(str(c) for c in x).strip() for x in df.columns]
cols = df.columns.tolist()
sc = next((c for c in cols if “Squad” in c), None)
vc = next((c for c in cols if c.strip() == col or c.endswith(f” {col}”)), None)
if sc and vc:
out = {}
for _, row in df.iterrows():
name = str(row[sc]).strip()
try:
val = float(str(row[vc]).replace(”,”, “.”))
if name and name.lower() not in (“squad”, “nan”):
out[name] = val
except:
pass
if out:
return out
except Exception as e:
print(f”[FBRef] {e}”)
return {}

def fbref_comp(comp_id):
if comp_id in fbref_cache:
return fbref_cache[comp_id]
s = get_current_season()
base = f”https://fbref.com/en/comps/{comp_id}/{s}-{s+1}”
shooting = fbref_table(f”{base}/shooting/”, “Sh/90”)
corners  = fbref_table(f”{base}/misc/”,     “CK”)
cards    = fbref_table(f”{base}/misc/”,     “CrdY”)
saves    = fbref_table(f”{base}/keepers/”,  “Saves”)
mp       = fbref_table(f”{base}/keepers/”,  “MP”)
data = {
team: {
“shots_p90”: shooting.get(team),
“corners”:   corners.get(team),
“yellow”:    cards.get(team),
“saves”:     saves.get(team),
“mp”:        mp.get(team),
}
for team in set(shooting) | set(corners) | set(cards)
}
fbref_cache[comp_id] = data
print(f”[FBRef] Comp {comp_id}: {len(data)} equipos”)
return data

# FIX #4: matching de equipos mejorado, evita falsos positivos por nombre parcial

def fbref_team(name, comp_id):
if not comp_id:
return None
data = fbref_comp(comp_id)
if not data:
return None

```
name_lower = name.lower().strip()

# 1. Match exacto
if name in data:
    return data[name]

# 2. Match exacto case-insensitive
for k, v in data.items():
    if k.lower() == name_lower:
        return v

# 3. Match por contención completa de alguna palabra larga (>= 4 chars)
name_words = [w for w in name_lower.split() if len(w) >= 4]
scored = []
for k, v in data.items():
    k_lower = k.lower()
    score = sum(1 for w in name_words if w in k_lower)
    if score > 0:
        scored.append((score, k, v))

if scored:
    scored.sort(key=lambda x: -x[0])
    # Solo devolver si el match es claro (score >= 1 y no hay empate entre candidatos)
    if len(scored) == 1 or scored[0][0] > scored[1][0]:
        return scored[0][2]

return None
```

def fbref_players(home, away, comp_id):
if not comp_id:
return []
s = get_current_season()
base  = f”https://fbref.com/en/comps/{comp_id}/{s}-{s+1}”
picks = []

```
def get_df(url):
    try:
        time.sleep(FBREF_DELAY + 1.0)
        r = requests.get(url, headers=FBREF_HEADERS, timeout=20)
        if r.status_code == 429:
            print(f"[FBRef players] Rate limited, esperando 60s...")
            time.sleep(60)
            r = requests.get(url, headers=FBREF_HEADERS, timeout=20)
        if r.status_code != 200:
            return None
        html = r.text.replace("<!--", "").replace("-->", "")
        for df in pd.read_html(StringIO(html)):
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = [" ".join(str(c) for c in x).strip() for x in df.columns]
            cols = df.columns.tolist()
            if next((c for c in cols if "Player" in c), None) and next((c for c in cols if "Squad" in c), None):
                return (df, cols)
    except:
        pass
    return None

# FIX #4 aplicado también a players: match de equipo mejorado
def squad_mask(df, scol, team_name):
    """Devuelve máscara usando las mismas palabras largas que fbref_team."""
    team_words = [w for w in team_name.lower().split() if len(w) >= 4]
    if not team_words:
        return df[scol].astype(str).str.lower().str.contains(team_name.lower().split()[0])
    mask = None
    for w in team_words:
        m = df[scol].astype(str).str.lower().str.contains(w)
        mask = m if mask is None else (mask | m)
    return mask

# Tiros a puerta
result = get_df(f"{base}/shooting/")
if result:
    try:
        df, cols = result
        pcol = next((c for c in cols if "Player" in c), None)
        scol = next((c for c in cols if "Squad" in c), None)
        vcol = next((c for c in cols if c.strip() == "SoT/90" or c.endswith(" SoT/90")), None)
        if pcol and scol and vcol:
            for team in [home, away]:
                mask = squad_mask(df, scol, team)
                tdf  = df[mask].copy()
                tdf["_v"] = pd.to_numeric(tdf[vcol], errors="coerce")
                for _, row in tdf.nlargest(2, "_v").iterrows():
                    try:
                        val = float(str(row[vcol]).replace(",", "."))
                        if val >= 1.0:
                            picks.append({"type": "player_sot", "player": str(row[pcol]).strip(),
                                          "team": team, "stat": f"Tiros a puerta: {val:.1f}/90"})
                    except:
                        pass
    except Exception as e:
        print(f"[FBRef players shooting] {e}")

# Paradas arquero
result = get_df(f"{base}/keepers/")
if result:
    try:
        df, cols = result
        pcol  = next((c for c in cols if "Player" in c), None)
        scol  = next((c for c in cols if "Squad" in c), None)
        mpcol = next((c for c in cols if c.strip() == "MP" or c.endswith(" MP")), None)
        svcol = next((c for c in cols if c.strip() == "Saves" or c.endswith(" Saves")), None)
        sppct = next((c for c in cols if "Save%" in c), None)
        if pcol and scol and mpcol and svcol:
            for team in [home, away]:
                mask = squad_mask(df, scol, team)
                tdf  = df[mask].copy()
                tdf["_mp"] = pd.to_numeric(tdf[mpcol], errors="coerce")
                for _, row in tdf.nlargest(1, "_mp").iterrows():
                    try:
                        sv = float(str(row[svcol]).replace(",", "."))
                        mp = float(str(row[mpcol]).replace(",", "."))
                        sp = float(str(row[sppct]).replace(",", ".")) if sppct else None
                        if mp > 0:
                            picks.append({"type": "keeper", "player": str(row[pcol]).strip(),
                                          "team": team, "stat": f"Paradas: {round(sv/mp,1)}/partido",
                                          "note": f"Save%: {sp}%" if sp else ""})
                    except:
                        pass
    except Exception as e:
        print(f"[FBRef players keepers] {e}")

return picks
```

# ── Análisis de mercados ──────────────────────────────────────────────────────

def _goals_from_list(goals_list):
“”“Stats de goles a partir de lista real de valores.”””
n = len(goals_list)
if n == 0:
return None
return {
“over25_prob”:  int(sum(1 for g in goals_list if g > 2.5) / n * 100),
“under25_prob”: int(sum(1 for g in goals_list if g < 2.5) / n * 100),
“over15_prob”:  int(sum(1 for g in goals_list if g > 1.5) / n * 100),
}

# FIX #2: probabilidades de goles via distribución de Poisson real

def poisson_prob_over(lam, threshold):
“”“P(X > threshold) usando distribución de Poisson con media lam.”””
if lam <= 0:
return 0
k = int(threshold)
# P(X > k) = 1 - P(X <= k)
prob_under_eq = sum(poisson.pmf(i, lam) for i in range(0, k + 1))
return max(0, min(int((1 - prob_under_eq) * 100), 95))

def poisson_prob_under(lam, threshold):
“”“P(X < threshold) usando distribución de Poisson con media lam.”””
if lam <= 0:
return 95
k = int(threshold)
prob_under = sum(poisson.pmf(i, lam) for i in range(0, k))
return max(0, min(int(prob_under * 100), 95))

def analyze_goals(home, away, league_id, fbref_id):
hid = team_id(home, league_id)
aid = team_id(away, league_id)

```
# ── H2H (≥4 partidos): usa datos reales directos ─────────────────────────
h2h = []
if hid and aid:
    h2h = apif("fixtures/headtohead", {"h2h": f"{hid}-{aid}", "last": 8, "status": "FT"})

if len(h2h) >= 4:
    goals, ht_goals, btts, hg_list, ag_list = [], [], [], [], []
    for g in h2h:
        hg  = g["goals"]["home"] or 0
        ag  = g["goals"]["away"] or 0
        hht = (g.get("score", {}).get("halftime", {}) or {}).get("home") or 0
        aht = (g.get("score", {}).get("halftime", {}) or {}).get("away") or 0
        goals.append(hg + ag)
        ht_goals.append(hht + aht)
        btts.append(1 if hg > 0 and ag > 0 else 0)
        if g["teams"]["home"]["id"] == hid:
            hg_list.append(hg); ag_list.append(ag)
        else:
            hg_list.append(ag); ag_list.append(hg)
    n = len(h2h)
    stats = _goals_from_list(goals)
    stats.update({
        "btts_prob":      int(sum(btts) / n * 100),
        "ht_over15_prob": int(sum(1 for g in ht_goals if g > 1.5) / n * 100),
        "home_goals":     hg_list,
        "away_goals":     ag_list,
        "avg_goals":      round(sum(goals) / n, 1),
        "sample":         n,
        "source":         "h2h",
    })
    return stats

# ── Forma reciente: Poisson con medias reales ─────────────────────────────
hf = team_form(hid) if hid else None
af = team_form(aid) if aid else None

if not hf or not af:
    return None

# Lambda para goles totales: goles esperados local + visitante
# Local ataca vs defensa visitante, y viceversa
lam_home = (hf["avg_for"] + af["avg_against"]) / 2
lam_away = (af["avg_for"] + hf["avg_against"]) / 2
lam_total = lam_home + lam_away
lam_ht    = (hf.get("avg_ht_for", 0.0) + af.get("avg_ht_for", 0.0)) / 2 * 2

# FIX #2: probabilidades via Poisson real
over25    = poisson_prob_over(lam_total, 2.5)
under25   = poisson_prob_under(lam_total, 2.5)   # P(X < 2.5) = P(X <= 2)
over15    = poisson_prob_over(lam_total, 1.5)
ht_over15 = poisson_prob_over(lam_ht,   1.5)

# BTTS: P(home >= 1) * P(away >= 1) = (1 - P(home=0)) * (1 - P(away=0))
p_home_scores = int((1 - poisson.pmf(0, lam_home)) * 100)
p_away_scores = int((1 - poisson.pmf(0, lam_away)) * 100)
btts_prob = int(p_home_scores * p_away_scores / 100)

return {
    "over25_prob":    over25,
    "under25_prob":   under25,
    "over15_prob":    over15,
    "btts_prob":      btts_prob,
    "ht_over15_prob": ht_over15,
    "home_goals":     hf.get("goals_list", []),
    "away_goals":     af.get("goals_list", []),
    "home_form":      hf["win_rate"],
    "away_form":      af["win_rate"],
    "avg_goals":      round(lam_total, 1),
    "sample":         min(hf["sample"], af["sample"]),
    "source":         "form",
}
```

# FIX #1: analyze_cc usa listas reales de partidos, no listas repetidas

def analyze_cc(home, away, league_id, fbref_id):
res = {k: None for k in [
“corners_total”, “corners_1h”, “corners_home”, “corners_away”,
“cards_total”,   “cards_1h”,   “cards_home”,   “cards_away”,
“corners_avg”,   “cards_avg”,  “source”,
]}
res[“source”] = “none”

```
# ── FBRef path: usa datos reales por partido (corners/mp, yellow/mp) ─────
# Convertimos promedios de temporada en estimados por partido.
# Luego usamos API-Football para obtener listas reales de los últimos partidos.
# FBRef solo se usa para filtrar si los promedios son coherentes.
fh = fbref_team(home, fbref_id)
fa = fbref_team(away, fbref_id)

# FIX #1: NO usamos [tc] * 8. En su lugar, intentamos API-Football primero
# para obtener listas reales. FBRef se usa solo para validación/promedio.
hid = team_id(home, league_id)
aid = team_id(away, league_id)

if hid and aid and load_req() < 80:
    hc_list, hk_list = fixture_corners_cards(hid, n=8)
    ac_list, ak_list = fixture_corners_cards(aid, n=8)

    # Listas totales partido a partido: sumamos por posición si tenemos ambas
    # Si una lista es más corta, usamos la más larga como referencia
    min_c = min(len(hc_list), len(ac_list))
    min_k = min(len(hk_list), len(ak_list))

    if min_c >= MIN_SAMPLE:
        tc_list = [hc_list[i] + ac_list[i] for i in range(min_c)]
        res["corners_total"] = find_best_line(tc_list, CORNER_LINES, "corners")
        res["corners_home"]  = find_best_line(hc_list[:min_c], [3.5, 4.5, 5.5, 6.5], f"corners ({home})")
        res["corners_away"]  = find_best_line(ac_list[:min_c], [3.5, 4.5, 5.5, 6.5], f"corners ({away})")
        res["corners_avg"]   = round(sum(tc_list) / len(tc_list), 1)
        res["source"]        = "api_football"

    if min_k >= MIN_SAMPLE:
        tk_list = [hk_list[i] + ak_list[i] for i in range(min_k)]
        res["cards_total"] = find_best_line(tk_list, CARD_LINES, "tarjetas")
        res["cards_home"]  = find_best_line(hk_list[:min_k], [0.5, 1.5, 2.5], f"tarjetas ({home})")
        res["cards_away"]  = find_best_line(ak_list[:min_k], [0.5, 1.5, 2.5], f"tarjetas ({away})")
        res["cards_avg"]   = round(sum(tk_list) / len(tk_list), 1)
        if res["source"] != "api_football":
            res["source"] = "api_football"

    # Si API-Football dio suficientes datos, retornar sin necesitar FBRef
    if res["corners_total"] is not None or res["cards_total"] is not None:
        return res

# Fallback a FBRef: solo si no tenemos datos reales de API-Football
# Y solo usamos el promedio de temporada como referencia informativa,
# NO como entrada a find_best_line (requiere MIN_SAMPLE datos reales).
if fh and fa:
    def pm(val, mp): return val / mp if val and mp and mp > 0 else None
    ch = pm(fh.get("corners"), fh.get("mp"))
    ca = pm(fa.get("corners"), fa.get("mp"))
    kh = pm(fh.get("yellow"),  fh.get("mp"))
    ka = pm(fa.get("yellow"),  fa.get("mp"))
    if ch and ca:
        res["corners_avg"] = round(ch + ca, 1)
        res["cards_avg"]   = round((kh or 0) + (ka or 0), 1)
        res["source"]      = "fbref_avg_only"
        # Nota: NO generamos picks de corners/cards solo con promedios FBRef
        # porque no tenemos distribución real. Solo reportamos el promedio.
        print(f"[FBRef fallback] {home} vs {away}: corners_avg={res['corners_avg']}, cards_avg={res['cards_avg']} (sin picks por muestra insuficiente)")

return res
```

def best_odds_pick(home, away, bookmakers, stats):
if not stats:
return None
candidates = []
MAP = {
(“h2h”,    home):        (“home_form”,   f”Gana {home}”),
(“h2h”,    away):        (“away_form”,   f”Gana {away}”),
(“totals”, “Over 2.5”):  (“over25_prob”, “Más de 2.5 goles”),
(“totals”, “Under 2.5”): (“under25_prob”,“Menos de 2.5 goles”),
(“totals”, “Over 1.5”):  (“over15_prob”, “Más de 1.5 goles”),
(“btts”,   “Yes”):       (“btts_prob”,   “Ambos equipos marcan”),
(“btts”,   “No”):        (None,          “No ambos marcan”),
}
for bm in bookmakers:
for market in bm.get(“markets”, []):
mk = market[“key”]
for outcome in market[“outcomes”]:
name, odd = outcome[“name”], float(outcome[“price”])
implied = round(1 / odd * 100, 1)
sp, label = None, name
for (k, n), (sk, lbl) in MAP.items():
if mk == k and (n.lower() in name.lower() or name.lower() in n.lower()):
sp = stats.get(sk) if sk else 100 - (stats.get(“btts_prob”) or 50)
label = lbl
break
if sp is None:
continue
value = sp - implied
if 1.30 <= odd <= 2.60 and sp >= 55 and value >= 2:
candidates.append({“bet”: label, “odd”: odd, “prob”: sp, “value”: round(value, 1)})
candidates.sort(key=lambda x: (x[“value”], x[“prob”]), reverse=True)
return candidates[0] if candidates else None

# ── Core ──────────────────────────────────────────────────────────────────────

def get_todays_picks():
today = datetime.now(TZ).strftime(”%Y-%m-%d”)
print(f”\n{’=’*50}\nAnálisis: {today} | APIF: {load_req()}/100\n{’=’*50}”)
odds_picks, stats_picks, player_picks = [], [], []
analyzed = 0

```
for sport_key, (flag, league_name, league_id, fbref_id) in LEAGUE_INFO.items():
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

            stats = analyze_goals(home, away, league_id, fbref_id)
            pick  = best_odds_pick(home, away, bm, stats)
            if pick:
                odds_picks.append({"match": f"{home} vs {away}", "league": f"{flag} {league_name}", **pick})

            # Goles local y visitante
            if stats:
                for goal_list, label in [
                    (stats.get("home_goals"), home),
                    (stats.get("away_goals"), away),
                ]:
                    if goal_list and len(goal_list) >= MIN_SAMPLE:
                        p = find_best_line(goal_list, [0.5, 1.5], f"goles ({label})")
                        if p:
                            stats_picks.append({
                                "match": f"{home} vs {away}", "league": f"{flag} {league_name}",
                                "bet": p["bet"], "prob": p["prob"],
                                "avg": stats["avg_goals"], "sample": stats["sample"], "source": "goals",
                            })

            cc = analyze_cc(home, away, league_id, fbref_id)
            for field in ["corners_total", "corners_1h", "corners_home", "corners_away",
                          "cards_total",   "cards_1h",   "cards_home",   "cards_away"]:
                p = cc.get(field)
                if p:
                    avg = cc.get("corners_avg") if "corner" in field else cc.get("cards_avg")
                    stats_picks.append({
                        "match": f"{home} vs {away}", "league": f"{flag} {league_name}",
                        "bet": p["bet"], "prob": p["prob"], "avg": avg,
                        "sample": "últimos partidos",
                        "source": cc["source"],
                    })

            if fbref_id:
                player_picks.extend(fbref_players(home, away, fbref_id))

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

return dedup(odds_picks)[:10], dedup(stats_picks)[:8], player_picks[:6]
```

def send_picks(odds_picks, stats_picks, player_picks, title=“Picks del día”):
sent_picks = load_sent_picks()  # FIX #6: cargar del disco
new_o = [p for p in odds_picks  if f”{p[‘match’]}-{p[‘bet’]}” not in sent_picks]
new_s = [p for p in stats_picks if f”{p[‘match’]}-{p[‘bet’]}” not in sent_picks]
if not new_o and not new_s and not player_picks:
print(“Sin picks nuevos”)
return

```
casa = "🟢 STAKE" if len(new_o) >= 2 else "🔵 1XBET"
msg  = f"🎯 <b>IVANPICKS — {title}</b>\n"
msg += f"📅 {datetime.now(TZ).strftime('%d/%m/%Y %H:%M')}\n\n"

if new_o:
    msg += f"🏦 <b>Casa: {casa}</b>\n\n"
    for i, p in enumerate(new_o, 1):
        msg += (f"<b>Pick {i}</b>\n⚽ {p['match']}\n🏆 {p['league']}\n"
                f"✅ {p['bet']}\n💰 Cuota: {p['odd']} | Prob: {p['prob']}% | Valor: +{p['value']}%\n\n")

if new_s:
    msg += "📊 <b>ANÁLISIS ESTADÍSTICO</b>\n<i>Buscá estas líneas en tu casa de apuestas</i>\n\n"
    for p in new_s:
        msg += f"⚽ {p['match']} | {p['league']}\n📌 {p['bet']}\n📈 Prob: {p['prob']}%"
        if p.get("avg"):
            msg += f" | Prom: {p['avg']}"
        msg += f" | Muestra: {p['sample']}\n\n"

if player_picks:
    msg += "👤 <b>STATS DE JUGADORES</b> <i>(FBRef)</i>\n\n"
    for p in player_picks:
        icon = "🧤" if p["type"] == "keeper" else "🎯"
        msg += f"{icon} <b>{p['player']}</b> ({p['team']})\n   {p['stat']}"
        if p.get("note"):
            msg += f" | {p['note']}"
        msg += "\n\n"

msg += "⚠️ Apostá con responsabilidad."
send_telegram(msg)

# FIX #6: guardar picks enviados en disco
for p in new_o + new_s:
    sent_picks.add(f"{p['match']}-{p['bet']}")
save_sent_picks(sent_picks)
```

# ── Scheduler ─────────────────────────────────────────────────────────────────

def daily_analysis():
print(”\n[CRON 03:00] Análisis diario…”)
# FIX #6: sent_picks se resetea en disco (load_sent_picks lo hace por fecha)
api_cache.clear()
# FIX #7: NO limpiar fbref_cache en ciclos de 2h; solo en análisis diario
fbref_cache.clear()
o, s, p = get_todays_picks()
send_picks(o, s, p, “Picks del día”)

def check_new_opportunities():
if not is_useful_hour() or load_req() >= MAX_API_REQ:
return
print(”[CRON 2H] Revisando…”)
# FIX #7: NO limpiar fbref_cache aquí — ya tiene los datos del día
api_cache.clear()  # Solo limpiamos API-Football para datos frescos
o, s, p = get_todays_picks()
sent_picks = load_sent_picks()
no = [x for x in o if f”{x[‘match’]}-{x[‘bet’]}” not in sent_picks]
ns = [x for x in s if f”{x[‘match’]}-{x[‘bet’]}” not in sent_picks]
if no or ns:
send_picks(no[:3], ns[:3], p[:2], “Nueva oportunidad!”)
else:
print(”[CRON 2H] Sin picks nuevos”)

if **name** == “**main**”:
print(“🤖 Bot IvanPicks iniciando…”)
send_telegram(“🤖 <b>Bot IvanPicks iniciado</b>\nFuentes: Odds API + API-Football + FBRef”)
daily_analysis()
schedule.every().day.at(“03:00”).do(daily_analysis)
schedule.every(2).hours.do(check_new_opportunities)
while True:
schedule.run_pending()
time.sleep(60)