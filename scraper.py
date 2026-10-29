#!/usr/bin/env python3
"""Descarga la red de webs de Wosti (futbolenlatv.es y gemelas) y genera site/data.json.

El mismo partido se identifica entre webs por el escudo de los dos equipos + hora UTC.
"""
import html
import json
import re
import sys
import time
import unicodedata
import urllib.request
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

# (clave web, idioma, dominio, zona horaria, formato fecha)
SITES = [
    ("es", "es", "www.futbolenlatv.es", "Europe/Madrid", "dmy"),
    ("mx", "lat", "www.futbolenvivomexico.com", "America/Mexico_City", "dmy"),
    ("ar", "lat", "www.futbolenvivoargentina.com", "America/Argentina/Buenos_Aires", "dmy"),
    ("co", "lat", "www.futbolenvivocolombia.com", "America/Bogota", "dmy"),
    ("us", "us", "www.futbolenvivousa.com", "America/New_York", "mdy"),
    ("uk", "en", "www.ukfootballontv.co.uk", "Europe/London", "dmy"),
    ("de", "de", "www.fussball-im-tv.com", "Europe/Berlin", "dmy"),
    ("it", "it", "www.calcio-tv.com", "Europe/Rome", "dmy"),
    ("fr", "fr", "www.foottv.fr", "Europe/Paris", "dmy"),
    ("pt", "pt", "www.futebolnatv.pt", "Europe/Lisbon", "dmy"),
    ("br", "br", "www.futebolaovivobrasil.com", "America/Sao_Paulo", "dmy"),
]
DAYS = 7
UA = "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"

RE_DATE = re.compile(r"(\d{1,2})[/.](\d{1,2})[/.](\d{4})")
RE_IMG = re.compile(r'img/\d+/([^"./]+)\.(?:webp|png|jpg)')
RE_HREF = re.compile(r'class="internalLink" href="([^"]+)"')
RE_SPAN_TITLE = re.compile(r'<span title="([^"]*)"')
RE_LI = re.compile(r'<li[^>]*title="([^"]*)"')
RE_HORA = re.compile(r'class="hora[^"]*">\s*(\d{1,2}):(\d{2})')

# Coletillas que no aportan nada: "(Ver en directo)", diales de operadores, etc.
RE_STRIP = [
    re.compile(r"\s*\((?:[^)]*(?:vivo|directo|diretta|direct|ansehen|live|acceder|plan plus))[^)]*\)", re.I),
    re.compile(r"\s*\((?:[MO]\d+\s*)+\)", re.I),
    re.compile(r"\s*\((?:canale \d+|\d[\d/ ]*(?:DirecTV)?)\)", re.I),
    re.compile(r"\s*:\s*VER PARTIDO.*$", re.I),
]
RE_DROP = re.compile(
    r"sin tv|por confirmar|to be confirmed|\btbc\b|da confermare|à confirmer|a confirmar|"
    r"noch offen|kein tv|no tv|sem tv|senza tv|pas de tv|\bbar\b|\bbares\b",
    re.I,
)

RE_REGIONAL = re.compile(
    r"dazn|sky|espn|bein|eurosport|amazon|prime|hbo|max\b|disney|paramount|tnt|fox|movistar|"
    r"sport ?tv|canal\+|star\+|vix|peacock|setanta|premier sports|viaplay|tv ?\d",
    re.I,
)


def clean_channel(name):
    name = html.unescape(name).strip()
    for rx in RE_STRIP:
        name = rx.sub("", name).strip()
    if not name or RE_DROP.search(name):
        return None
    return name


def fetch(domain):
    for attempt in range(3):
        try:
            req = urllib.request.Request(f"https://{domain}/", headers={"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            print(f"[{domain}] intento {attempt + 1}: {e}", file=sys.stderr)
            time.sleep(3)
    return None


def parse(site, page):
    key, lang, domain, tzname, datefmt = site
    tz = ZoneInfo(tzname)
    start = page.find('<table class="tablaPrincipal')
    end = page.rfind("</table>")
    if start < 0:
        return []
    body = page[start:end]
    day = comp = None
    out = []
    for chunk in body.split("<tr")[1:]:
        if chunk.startswith(' class="cabeceraTabla'):
            m = RE_DATE.search(chunk)
            if m:
                a, b, y = map(int, m.groups())
                d, mo = (b, a) if datefmt == "mdy" else (a, b)
                day = (y, mo, d)
            continue
        if chunk.startswith(' class="cabeceraCompericion'):
            img = RE_IMG.search(chunk)
            href = RE_HREF.search(chunk)
            name = re.search(r'title="([^"]*)"', chunk)
            slug = href.group(1).rstrip("/").split("/")[-1] if href else html.unescape(name.group(1) if name else "?")
            comp = {
                "slug": slug,
                "name": html.unescape(name.group(1)).strip() if name else slug,
                "logo": img.group(1) if img else None,
            }
            continue
        hm = RE_HORA.search(chunk)
        if not hm or not day or not comp or 'class="local"' not in chunk:
            continue
        local_part = chunk[chunk.find('class="local"'):chunk.find('class="visitante"')]
        away_part = chunk[chunk.find('class="visitante"'):chunk.find('class="canales"')]
        teams = []
        for part in (local_part, away_part):
            img = RE_IMG.search(part)
            nm = RE_SPAN_TITLE.search(part)
            href = RE_HREF.search(part)
            teams.append({
                "logo": img.group(1) if img else None,
                "name": html.unescape(nm.group(1)).strip() if nm else "?",
                "slug": href.group(1).rstrip("/").split("/")[-1] if href else None,
            })
        det = chunk[chunk.find('class="detalles'):chunk.find('class="local"')]
        rnd = RE_SPAN_TITLE.search(det)
        canales = chunk[chunk.find('class="listaCanales"'):]
        chans = []
        for c in RE_LI.findall(canales):
            c = clean_channel(c)
            if c and c not in chans:
                chans.append(c)
        dt = datetime(*day, int(hm.group(1)), int(hm.group(2)), tzinfo=tz)
        out.append({
            "site": key,
            "lang": lang,
            "t": int(dt.timestamp()),
            "comp": comp,
            "round": html.unescape(rnd.group(1)).strip() if rnd else "",
            "home": teams[0],
            "away": teams[1],
            "chans": chans,
        })
    return out


def team_key(t, generic):
    if t["logo"] and t["logo"] not in generic:
        return t["logo"]
    return "n:" + (t["slug"] or t["name"]).lower()


def build(rows_by_site):
    # Escudos genéricos (el mismo para muchos equipos distintos) no sirven como identificador
    logo_names = defaultdict(set)
    for rows in rows_by_site.values():
        for r in rows:
            for t in (r["home"], r["away"]):
                if t["logo"] and t["slug"]:
                    logo_names[t["logo"]].add(t["slug"])
    generic = {logo for logo, s in logo_names.items() if len(s) > 3}

    now = int(time.time())
    first_day = datetime.now(ZoneInfo("Europe/Madrid")).replace(hour=0, minute=0, second=0, microsecond=0)
    t_min = int(first_day.timestamp()) - 12 * 3600
    t_max = int((first_day + timedelta(days=DAYS)).timestamp()) + 12 * 3600

    teams, comps, matches = {}, {}, {}
    comp_map = {}  # (site, slug) -> comp id base (de futbolenlatv.es)
    order = [s[0] for s in SITES]  # es primero: sus nombres mandan

    # 1) es como base; 2) resto se fusiona; los partidos que solo existen fuera se añaden
    pending_comp_votes = defaultdict(Counter)
    for site_key in order:
        for r in rows_by_site.get(site_key, []):
            if not (t_min <= r["t"] <= t_max):
                continue
            h, a = team_key(r["home"], generic), team_key(r["away"], generic)
            mid = f"{h}|{a}|{r['t']}"
            if mid not in matches:
                # tolerancia: algunas webs aplican mal el cambio de hora a días futuros (±1 h)
                for dt in (-3600, 3600, -1800, 1800, -900, 900):
                    alt = f"{h}|{a}|{r['t'] + dt}"
                    if alt in matches:
                        mid = alt
                        break
            for tk, t in ((h, r["home"]), (a, r["away"])):
                if tk not in teams:
                    teams[tk] = {"n": t["name"], "l": t["logo"] if tk == t["logo"] else None}
            cs = (site_key, r["comp"]["slug"])
            if mid in matches:
                m = matches[mid]
                if not m["c"].startswith(f"{site_key}:"):
                    pending_comp_votes[cs][m["c"]] += 1
            else:
                cid = comp_map.get(cs)
                if cid is None:
                    cid = r["comp"]["slug"] if site_key == "es" else f"{site_key}:{r['comp']['slug']}"
                    comp_map[cs] = cid
                if cid not in comps:
                    comps[cid] = {"n": r["comp"]["name"], "l": r["comp"]["logo"], "o": len(comps)}
                m = matches[mid] = {"id": mid, "t": r["t"], "c": cid, "r": r["round"], "h": h, "a": a, "ch": {}}
            lst = m["ch"].setdefault(r["lang"], [])
            for c in r["chans"]:
                if c not in lst:
                    lst.append(c)

    # Competiciones de otras webs que en realidad son una de es → reasignar sus partidos sin pareja
    remap = {}
    for (site_key, slug), votes in pending_comp_votes.items():
        if site_key == "es" or not votes:
            continue
        remap[f"{site_key}:{slug}"] = votes.most_common(1)[0][0]
    for m in matches.values():
        seen = set()
        while m["c"] in remap and m["c"] not in seen:
            seen.add(m["c"])
            m["c"] = remap[m["c"]]

    # Misma competición con distinta cabecera (con/sin enlace, o en dos webs): unir por nombre y por slug
    canon = {}
    def pref(c):  # es antes que el resto; con enlace (slug) antes que sin él
        return (":" in c, not re.fullmatch(r"[a-z0-9-]+", c.split(":")[-1]), comps[c]["o"])
    for cid in sorted(comps, key=pref):
        for k in ("n:" + comps[cid]["n"].lower(), "s:" + cid.split(":")[-1].lower()):
            canon.setdefault(k, cid)
    for m in matches.values():
        m["c"] = canon.get("s:" + m["c"].split(":")[-1].lower(), m["c"])
        m["c"] = canon.get("n:" + comps[m["c"]]["n"].lower(), m["c"])

    # Canales presentes en 3+ idiomas del mismo partido (OneFootball, YouTube…) → internacional,
    # salvo marcas que en cada país son un canal distinto (DAZN España ≠ DAZN Alemania)
    for m in matches.values():
        cnt = Counter(c for lst in m["ch"].values() for c in set(lst))
        intl = [c for c, k in cnt.items() if k >= 3 and not RE_REGIONAL.search(c)]
        if intl:
            for lang in list(m["ch"]):
                m["ch"][lang] = [c for c in m["ch"][lang] if c not in intl]
                if not m["ch"][lang]:
                    del m["ch"][lang]
            m["ch"]["int"] = sorted(intl)

    # Id estable entre ejecuciones (los favoritos del móvil dependen de él): nombre normalizado
    def slugify(t):
        t = unicodedata.normalize("NFKD", t.lower()).encode("ascii", "ignore").decode()
        return re.sub(r"[^a-z0-9]+", "-", t).strip("-")
    final = {}
    for m in matches.values():
        old = m["c"]
        m["c"] = slugify(comps[old]["n"])
        final.setdefault(m["c"], comps[old])
    comps = final

    # Orden por defecto: competiciones con más idiomas emitiendo primero (aproxima su relevancia)
    pop = defaultdict(list)
    for m in matches.values():
        pop[m["c"]].append(len([lang for lang in m["ch"] if lang != "int"]))
    for rank, cid in enumerate(sorted(pop, key=lambda c: -sum(pop[c]) / len(pop[c]) - 0.02 * len(pop[c]))):
        comps[cid]["o"] = rank

    used_comps = {m["c"] for m in matches.values()}
    used_teams = {k for m in matches.values() for k in (m["h"], m["a"])}
    return {
        "generated": now,
        "comps": {k: v for k, v in comps.items() if k in used_comps},
        "teams": {k: v for k, v in teams.items() if k in used_teams},
        "matches": sorted(matches.values(), key=lambda m: (m["t"], comps[m["c"]]["o"])),
    }


def main():
    out_path = Path(sys.argv[1] if len(sys.argv) > 1 else "site/data.json")
    with ThreadPoolExecutor(6) as ex:
        pages = dict(zip([s[0] for s in SITES], ex.map(lambda s: fetch(s[2]), SITES)))
    rows = {}
    for s in SITES:
        page = pages[s[0]]
        rows[s[0]] = parse(s, page) if page else []
        print(f"{s[0]}: {len(rows[s[0]])} partidos", file=sys.stderr)
    if not rows["es"]:
        sys.exit("futbolenlatv.es no devolvió datos; no se sobrescribe data.json")
    data = build(rows)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"{len(data['matches'])} partidos, {len(data['comps'])} competiciones → {out_path}", file=sys.stderr)


if __name__ == "__main__":
    main()
