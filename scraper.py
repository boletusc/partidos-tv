#!/usr/bin/env python3
"""Descarga la red de webs de Wosti (futbolenlatv.es y gemelas) y genera site/data-<deporte>.json.

El mismo partido se identifica entre webs por el escudo (o el nombre) de los dos rivales + hora UTC.
Cada deporte va en su propio archivo: si uno falla, se conserva el anterior y el resto sigue.
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

# (clave web, idioma, dominio, zona horaria, formato fecha, prefijo de las páginas de otros deportes)
SITES = [
    ("es", "es", "www.futbolenlatv.es", "Europe/Madrid", "dmy", "/deporte/"),
    ("mx", "lat", "www.futbolenvivomexico.com", "America/Mexico_City", "dmy", "/deporte/"),
    ("ar", "lat", "www.futbolenvivoargentina.com", "America/Argentina/Buenos_Aires", "dmy", "/deporte/"),
    ("co", "lat", "www.futbolenvivocolombia.com", "America/Bogota", "dmy", "/deporte/"),
    ("us", "us", "www.futbolenvivousa.com", "America/New_York", "mdy", "/deporte/"),
    ("uk", "en", "www.ukfootballontv.co.uk", "Europe/London", "dmy", "/sport/"),
    ("de", "de", "www.fussball-im-tv.com", "Europe/Berlin", "dmy", "/sport/"),
    ("it", "it", "www.calcio-tv.com", "Europe/Rome", "dmy", "/sport/"),
    ("fr", "fr", "www.foottv.fr", "Europe/Paris", "dmy", "/sport/"),
    ("pt", "pt", "www.futebolnatv.pt", "Europe/Lisbon", "dmy", "/sport/"),
    ("br", "br", "www.futebolaovivobrasil.com", "America/Sao_Paulo", "dmy", "/esporte/"),
]
# deporte → slug de su página (la web alemana usa los suyos); fútbol es la portada
SPORTS = {
    "futbol": None,
    "baloncesto": {"*": "baloncesto", "de": "basketball"},
    "tenis": {"*": "tenis", "de": "tennis"},
    "motos": {"*": "motociclismo", "de": "motorradrennen"},
    "coches": {"*": "automovilismo", "de": "autorennen"},
}
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


# Orden por defecto (sin favoritos), al estilo FotMob/BeSoccer para un usuario español.
# Expresiones sobre el nombre normalizado de la competición; lo no listado va detrás, por relevancia.
PRIORITY = {
    "futbol": [
        # España
        r"^la ?liga ea", r"^copa del rey$", r"^supercopa de espana$", r"^la ?liga hypermotion", r"^primera federacion$",
        r"^segunda federacion$", r"^tercera federacion$",
        # Selecciones y Europa
        r"^mundial$|^copa del mundo$|^fifa mundial$", r"^eurocopa$", r"clasificacion (mundial|eurocopa)", r"^uefa nations league$",
        r"amistos", r"^champions league$", r"^europa league$", r"^conference league$", r"supercopa de europa|uefa super cup",
        r"mundial de clubes",
        # Inglaterra
        r"^premier league$", r"^fa cup$|^copa fa$|^copa de inglaterra$", r"^efl carabao cup$|^copa de la liga inglesa",
        r"community shield", r"^championship$", r"^league one$", r"^league two$", r"^efl trophy$", r"^national league$",
        # Italia, Alemania, Francia, Portugal
        r"^serie a italiana$", r"^coppa italia$|^copa de italia$", r"supercoppa|supercopa de italia", r"^serie b italiana$",
        r"^bundesliga$", r"^dfb pokal$|^copa de alemania$", r"^2 bundesliga$", r"^3 liga$",
        r"^francia ligue 1$|^ligue 1$", r"^copa de francia$|^coupe de france$", r"^ligue 2$",
        r"^liga portuguesa$", r"^copa de portugal$|^taca de portugal$", r"^allianz cup$", r"^liga portugal 2$",
        # Resto de Europa
        r"^eredivisie$", r"^jupiler pro league$", r"^superliga turca$", r"^premiership$", r"^scottish", r"^superliga grecia$",
        r"^saudi pro league$",
        # América
        r"^copa libertadores$", r"^copa sudamericana$", r"^liga mx$", r"^primera division argentina$|^liga profesional argentina",
        r"^copa argentina$", r"^serie a brasil$|^brasileirao$", r"^copa do brasil$", r"^mls$", r"^liga colombiana$",
        r"concacaf champions",
    ],
    "baloncesto": [r"^nba$", r"^euroliga$", r"^liga endesa$", r"^copa del rey$", r"^supercopa", r"^eurocup$",
                   r"^basketball champions league$", r"^fiba europe cup$", r"^primera feb$", r"^wnba$"],
    "tenis": [r"grand slam|open de australia|roland garros|wimbledon|us open|atp finals|copa davis", r"masters", r"^atp"],
    "motos": [r"^motogp$", r"^moto2$", r"^moto3$", r"superbike"],
    "coches": [r"^formula 1$", r"^formula 2$", r"^formula 3$"],
}


# Siempre al fondo: primero cantera/juveniles y, lo último, todo lo femenino
RE_YOUTH = re.compile(r"sub ?\d|\bu ?\d\d\b|juvenil|youth|primavera|academy|cadete|infantil|reserva|proyeccion|junioren|liga u$")
RE_WOMEN = re.compile(r"femenin|women|frauen|femminile|feminine|feminin|femenil|damallsvenskan|^liga f$|copa de la reina|"
                      r"\bwnba\b|\bnwsl\b|\bd1 feminine|usl super league|liga bpi")


def clean_channel(name):
    name = html.unescape(name).strip()
    for rx in RE_STRIP:
        name = rx.sub("", name).strip()
    if not name or RE_DROP.search(name):
        return None
    return name


def site_url(site, sport):
    slugs = SPORTS[sport]
    if not slugs:
        return f"https://{site[2]}/"
    return f"https://{site[2]}{site[5]}{slugs.get(site[0], slugs['*'])}"


def fetch(url):
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9"})
            with urllib.request.urlopen(req, timeout=40) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # noqa: BLE001
            print(f"[{url}] intento {attempt + 1}: {e}", file=sys.stderr)
            time.sleep(3)
    return None


def norm_name(t):
    t = unicodedata.normalize("NFKD", html.unescape(t).lower()).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", " ", t).strip()


def parse(site, page):
    key, lang, domain, tzname, datefmt, _ = site
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
        if not day or not (hm or 'class="hora' in chunk):
            continue  # sin hora ("PD", por determinar) sirve para el catálogo de equipos
        is_event = 'class="eventoUnaColumna' in chunk
        if not is_event and 'class="local"' not in chunk:
            continue
        det_end = chunk.find('class="eventoUnaColumna' if is_event else 'class="local"')
        det = chunk[chunk.find('class="detalles'):det_end]
        # En las páginas de otros deportes la competición va en cada fila, no en una cabecera
        cimg = re.search(r'<img src="[^"]*img/\d+/([^"./]+)\.webp"[^>]*title="([^"]*)"', det)
        row_comp = comp
        if cimg:
            href = RE_HREF.search(det)
            cname = html.unescape(cimg.group(2)).strip()
            row_comp = {
                "slug": href.group(1).rstrip("/").split("/")[-1] if href else cname,
                "name": cname,
                "logo": cimg.group(1),
            }
        if not row_comp:
            continue
        if is_event:
            ev = re.search(r'class="eventoUnico">(.*?)</span>', chunk, re.S)
            text = re.sub(r"\s*<br\s*/?>\s*", " · ", ev.group(1)) if ev else ""
            text = html.unescape(re.sub(r"<[^>]+>", "", text)).strip(" ·")
            teams = [{"logo": None, "name": text, "slug": None}, None]
        else:
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
        rnd = RE_SPAN_TITLE.search(det)
        canales = chunk[chunk.find('class="listaCanales"'):]
        chans = []
        for c in RE_LI.findall(canales):
            c = clean_channel(c)
            if c and c not in chans:
                chans.append(c)
        dt = datetime(*day, int(hm.group(1)), int(hm.group(2)), tzinfo=tz) if hm else None
        out.append({
            "site": key,
            "lang": lang,
            "t": int(dt.timestamp()) if dt else None,
            "comp": row_comp,
            "event": is_event,
            "round": html.unescape(rnd.group(1)).strip() if rnd else "",
            "home": teams[0],
            "away": teams[1],
            "chans": chans,
        })
    return out


def team_key(t, generic, sport):
    if t["logo"] and t["logo"] not in generic:
        return t["logo"]
    if t["logo"] and sport == "futbol":  # escudo compartido (Real Madrid / RM Castilla): escudo + nombre
        return f"{t['logo']}~{norm_name(t['name'])}"
    return f"n:{sport}:{norm_name(t['name'])}"


def build(rows_by_site, sport, shared_logos=frozenset()):
    # Un escudo que en una misma web lleva dos nombres distintos es genérico (p. ej. la bandera
    # de un tenista) y no sirve como identificador: entonces se usa el nombre
    logo_names = defaultdict(set)
    for site_key, rows in rows_by_site.items():
        for r in rows:
            for t in (r["home"], r["away"]):
                if t and t["logo"] and (t["slug"] or sport != "futbol"):
                    logo_names[t["logo"]].add((site_key, t["slug"] or norm_name(t["name"])))
    if sport == "futbol":
        # estable entre ejecuciones (los favoritos dependen de ello): escudos que el índice de clubes
        # asigna a varios equipos (Real Madrid / RM Castilla) + los muy repetidos (escudo genérico)
        generic = set(shared_logos) | {logo for logo, names in logo_names.items() if len({n for _, n in names}) > 3}
    else:
        generic = {logo for logo, names in logo_names.items()
                   if max(Counter(sk for sk, _ in names).values()) > 1}

    now = int(time.time())
    first_day = datetime.now(ZoneInfo("Europe/Madrid")).replace(hour=0, minute=0, second=0, microsecond=0)
    t_min = int(first_day.timestamp()) - 12 * 3600
    t_max = int((first_day + timedelta(days=DAYS)).timestamp()) + 12 * 3600

    teams, comps, matches = {}, {}, {}
    loose = {}  # escudo-escudo-hora → id del partido
    comp_map = {}  # (site, slug) -> comp id base (de futbolenlatv.es)
    order = [s[0] for s in SITES]  # es primero: sus nombres mandan

    # 1) es como base; 2) resto se fusiona; los partidos que solo existen fuera se añaden
    pending_comp_votes = defaultdict(Counter)
    for site_key in order:
        for r in rows_by_site.get(site_key, []):
            if not r["t"] or not (t_min <= r["t"] <= t_max):
                continue
            if r["event"]:  # GP, carrera…: se identifica por la competición (MotoGP, F1…) y la hora
                h, a = "ev:" + (r["comp"]["logo"] or norm_name(r["comp"]["name"])), ""
                tolerance = (-3600, 3600)
            else:
                h, a = team_key(r["home"], generic, sport), team_key(r["away"], generic, sport)
                tolerance = (-3600, 3600, -1800, 1800, -900, 900)
            mid = f"{h}|{a}|{r['t']}"
            if mid not in matches:
                # tolerancia: algunas webs aplican mal el cambio de hora a días futuros (±1 h);
                # y con escudo compartido el nombre va traducido, así que se compara solo el escudo
                lh, la = h.split("~")[0], a.split("~")[0]
                for dt in (0, *tolerance):
                    alt = loose.get(f"{lh}|{la}|{r['t'] + dt}")
                    if alt:
                        mid = alt
                        break
            loose.setdefault(f"{h.split('~')[0]}|{a.split('~')[0]}|{r['t']}", mid)
            if not r["event"]:
                for tk, t in ((h, r["home"]), (a, r["away"])):
                    if tk not in teams:
                        teams[tk] = {"n": t["name"], "l": t["logo"]}
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
                if r["event"]:
                    m.update(h=None, a=None, e=r["home"]["name"])
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
        m["c"] = slugify(comps[old]["n"]) if sport == "futbol" else f"{sport}:{slugify(comps[old]['n'])}"
        final.setdefault(m["c"], comps[old])
    comps = final

    # Orden por defecto: competiciones con más idiomas emitiendo primero (aproxima su relevancia)
    pop = defaultdict(list)
    for m in matches.values():
        pop[m["c"]].append(len([lang for lang in m["ch"] if lang != "int"]))
    prio = [re.compile(rx) for rx in PRIORITY.get(sport, [])]
    def prio_of(cid):
        n = norm_name(comps[cid]["n"])
        tier = 2 if RE_WOMEN.search(n) else 1 if RE_YOUTH.search(n) else 0
        return tier, next((i for i, rx in enumerate(prio) if rx.search(n)), len(prio))
    by_pop = sorted(pop, key=lambda c: -sum(pop[c]) / len(pop[c]) - 0.02 * len(pop[c]))
    for rank, cid in enumerate(sorted(by_pop, key=prio_of)):  # sort estable: dentro de cada nivel, relevancia
        comps[cid]["o"] = rank

    # Catálogo para el buscador de favoritos: todos los equipos/competiciones de las páginas,
    # aunque no jueguen esta semana (se acumula entre ejecuciones en main)
    cat_teams, cat_comps = {}, {}
    for site_key in order:
        for r in rows_by_site.get(site_key, []):
            if r["event"]:
                continue
            for t in (r["home"], r["away"]):
                tk = team_key(t, generic, sport)
                cat_teams.setdefault(tk, {"n": t["name"], "l": t["logo"]})
            if site_key == "es":
                cid = slugify(r["comp"]["name"])
                cat_comps.setdefault(cid if sport == "futbol" else f"{sport}:{cid}", {"n": r["comp"]["name"], "l": r["comp"]["logo"]})
    for cid, c in comps.items():
        cat_comps[cid] = {"n": c["n"], "l": c["l"]}
    for tk, t in teams.items():
        cat_teams[tk] = {"n": t["n"], "l": t["l"]}

    used_comps = {m["c"] for m in matches.values()}
    used_teams = {k for m in matches.values() for k in (m["h"], m["a"]) if k}
    return {"teams": cat_teams, "comps": cat_comps, "generic": generic}, {
        "generated": now,
        "sport": sport,
        "comps": {k: v for k, v in comps.items() if k in used_comps},
        "teams": {k: v for k, v in teams.items() if k in used_teams},
        "matches": sorted(matches.values(), key=lambda m: (m["t"], comps[m["c"]]["o"])),
    }


def main():
    out_dir = Path(sys.argv[1] if len(sys.argv) > 1 else "site")
    jobs = [(sport, site) for sport in SPORTS for site in SITES]
    with ThreadPoolExecutor(6) as ex:
        pages = dict(zip([(sp, si[0]) for sp, si in jobs], ex.map(lambda j: fetch(site_url(j[1], j[0])), jobs)))
    # Índice de clubes de futbolenlatv.es (≈1.200 equipos con escudo) para buscar favoritos
    idx = fetch("https://www.futbolenlatv.es/equipo") or ""
    club_index = [(m.group(1), html.unescape(m.group(2)).strip()) for m in re.finditer(
        r'<img src="[^"]*img/\d+/([^"./]+)\.(?:webp|png)"[^>]*title="([^"]*)"[^>]*>\s*(?:</a>\s*)?<a href="/equipo/', idx)]
    club_index += [(m.group(1), html.unescape(m.group(2)).strip()) for m in re.finditer(
        r'href="/equipo/[^"]+">\s*<img src="[^"]*img/\d+/([^"./]+)\.(?:webp|png)"[^>]*title="([^"]*)"', idx)]
    names_by_logo = defaultdict(set)
    for logo, name in club_index:
        names_by_logo[logo].add(name)
    shared_logos = frozenset(lg for lg, ns in names_by_logo.items() if len(ns) > 1)
    print(f"índice de clubes: {len(club_index)} ({len(shared_logos)} escudos compartidos)", file=sys.stderr)
    ok = 0
    for sport in SPORTS:
        rows = {}
        for site in SITES:
            page = pages[(sport, site[0])]
            rows[site[0]] = parse(site, page) if page else []
        print(f"{sport}: " + " ".join(f"{k}={len(v)}" for k, v in rows.items()), file=sys.stderr)
        out = out_dir / f"data-{sport}.json"
        if not rows["es"]:
            print(f"  futbolenlatv.es no devolvió {sport}; se conserva el archivo anterior", file=sys.stderr)
            continue
        cat, data = build(rows, sport, shared_logos if sport == "futbol" else frozenset())
        generic_futbol = cat.pop("generic")
        if sport == "futbol" and club_index:
            for logo, name in club_index:
                tk = team_key({"logo": logo, "name": name, "slug": None}, generic_futbol, "futbol")
                cat["teams"].setdefault(tk, {"n": name, "l": logo})
        cat_path = out_dir / f"cat-{sport}.json"
        try:
            old = json.loads(cat_path.read_text(encoding="utf-8"))
            for k in ("teams", "comps"):
                cat[k] = {**old.get(k, {}), **cat[k]}
        except (OSError, ValueError):
            pass
        out_dir.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        cat_path.write_text(json.dumps(cat, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
        ok += 1
        print(f"  {len(data['matches'])} partidos, {len(data['comps'])} competiciones → {out}", file=sys.stderr)
    if not ok:
        sys.exit("ningún deporte se pudo actualizar")


if __name__ == "__main__":
    main()
