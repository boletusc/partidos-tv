"use strict";

const LANGS = [
  { k: "es", f: "🇪🇸", n: "Castellano" },
  { k: "lat", f: "🇲🇽", n: "Español latino" },
  { k: "us", f: "🇺🇸", n: "EE. UU. (inglés y español)" },
  { k: "en", f: "🇬🇧", n: "Inglés (Reino Unido)" },
  { k: "de", f: "🇩🇪", n: "Alemán" },
  { k: "it", f: "🇮🇹", n: "Italiano" },
  { k: "fr", f: "🇫🇷", n: "Francés" },
  { k: "pt", f: "🇵🇹", n: "Portugués (Portugal)" },
  { k: "br", f: "🇧🇷", n: "Portugués (Brasil)" },
  { k: "int", f: "🌐", n: "Internacional (YouTube, OneFootball…)" },
];
const LANG = Object.fromEntries(LANGS.map(l => [l.k, l]));
// d: duración aproximada en minutos (para marcar "EN VIVO" y atenuar lo ya terminado)
const SPORTS = [
  { k: "futbol", f: "⚽", n: "Fútbol", d: 115 },
  { k: "baloncesto", f: "🏀", n: "Baloncesto", d: 140 },
  { k: "tenis", f: "🎾", n: "Tenis", d: 150 },
  { k: "motos", f: "🏍️", n: "Motociclismo", d: 60 },
  { k: "coches", f: "🏎️", n: "Automovilismo (F1…)", d: 120 },
];
const SPORT = Object.fromEntries(SPORTS.map(x => [x.k, x]));
const sportOf = compId => compId.includes(":") ? compId.split(":")[0] : "futbol";
const LOGO = id => id ? `https://static.futbolenlatv.com/img/32/${id}.webp` : "";

/* ---------- estado persistente ---------- */
const store = {
  get(k, def) { try { const v = localStorage.getItem("ptv." + k); return v === null ? def : JSON.parse(v); } catch { return def; } },
  set(k, v) { try { localStorage.setItem("ptv." + k, JSON.stringify(v)); } catch {} },
};
const S = {
  sports: store.get("sports", ["futbol"]),
  langs: store.get("langs", ["es", "lat", "en"]),
  onlyTv: store.get("onlyTv", true),
  favTeams: store.get("favTeams", []),   // [{id, n, l}]
  favComps: store.get("favComps", []),   // [{id, n, l}] en el orden elegido
  showOthers: store.get("showOthers", true),
  closed: new Set(store.get("closed", [])),
};
const save = () => {
  store.set("sports", S.sports); store.set("langs", S.langs); store.set("onlyTv", S.onlyTv);
  store.set("favTeams", S.favTeams); store.set("favComps", S.favComps);
  store.set("showOthers", S.showOthers); store.set("closed", [...S.closed]);
};

const SD = {};      // datos por deporte, tal cual llegan
let DATA = null;   // unión de los deportes seleccionados
// Python norm_name: los favoritos con escudo compartido usan "escudo~nombre" como id
const pyNorm = s => s.normalize("NFKD").replace(/[\u0300-\u036f]/g, "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
function migrateFavs() {
  let changed = false;
  for (const f of S.favTeams) {
    if (f.id.includes("~") || f.id.startsWith("n:")) continue;
    const alt = f.id + "~" + pyNorm(f.n);
    if (findIn("teams", alt)) { f.id = alt; changed = true; }
  }
  if (changed) save();
}
function mergeData() {
  const parts = S.sports.map(k => SD[k]).filter(Boolean);
  if (!parts.length) { DATA = S.sports.length ? null : { comps: {}, teams: {}, matches: [], generated: 0 }; return; }
  DATA = {
    generated: Math.min(...parts.map(p => p.generated)),
    comps: Object.assign({}, ...parts.map(p => p.comps)),
    teams: Object.assign({}, ...parts.map(p => p.teams)),
    matches: parts.flatMap(p => p.matches.map(m => (m.s = p.sport, m))).sort((x, y) => x.t - y.t),
  };
  migrateFavs();
}
let dayIdx = 0;
const $ = s => document.querySelector(s);
const esc = s => String(s).replace(/[&<>"]/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const norm = s => s.normalize("NFD").replace(/[̀-ͯ]/g, "").toLowerCase();
const isFavTeam = id => S.favTeams.some(t => t.id === id);
const isFavComp = id => S.favComps.some(c => c.id === id);
const now = () => Date.now() / 1000;

/* ---------- días ---------- */
function startOfDay(offset) {
  const d = new Date(); d.setHours(0, 0, 0, 0); d.setDate(d.getDate() + offset);
  return d.getTime() / 1000;
}
function dayLabel(i) {
  if (i === 0) return "Hoy";
  if (i === 1) return "Mañana";
  const d = new Date(startOfDay(i) * 1000);
  return d.toLocaleDateString("es-ES", { weekday: "short", day: "numeric" }).replace(".", "");
}
const fmtTime = t => new Date(t * 1000).toLocaleTimeString("es-ES", { hour: "2-digit", minute: "2-digit" });

/* ---------- render cabecera ---------- */
function renderDays() {
  const el = $("#days");
  el.innerHTML = Array.from({ length: 7 }, (_, i) =>
    `<button class="day${i === dayIdx ? " on" : ""}" data-d="${i}">${dayLabel(i)}</button>`).join("");
  el.querySelector(".on")?.scrollIntoView({ inline: "center", block: "nearest" });
}
function renderSports() {
  $("#sports").innerHTML = SPORTS.map(x =>
    `<button class="flag sport${S.sports.includes(x.k) ? " on" : ""}" data-s="${x.k}" title="${esc(x.n)}">${x.f}</button>`).join("");
}
$("#sports").addEventListener("click", e => {
  const b = e.target.closest("[data-s]"); if (!b) return;
  const k = b.dataset.s;
  S.sports = S.sports.includes(k) ? S.sports.filter(x => x !== k) : SPORTS.map(x => x.k).filter(x => x === k || S.sports.includes(x));
  save(); renderSports(); mergeData(); renderList(); renderFoot();
  if (S.sports.includes(k) && !SD[k]) loadSport(k).then(() => { mergeData(); renderList(); renderFoot(); });
});
function renderLangs() {
  $("#langs").innerHTML =
    LANGS.map(l => `<button class="flag${S.langs.includes(l.k) ? " on" : ""}" data-l="${l.k}" title="${esc(l.n)}">${l.f}</button>`).join("") +
    `<button class="flag tv${S.onlyTv ? " on" : ""}" data-tv="1" title="Ocultar partidos sin canal en tus idiomas">📺 Con TV</button>`;
}
$("#days").addEventListener("click", e => {
  const b = e.target.closest("[data-d]"); if (!b) return;
  dayIdx = +b.dataset.d; renderDays(); renderList(); window.scrollTo({ top: 0 });
});
$("#langs").addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  if (b.dataset.tv) S.onlyTv = !S.onlyTv;
  else {
    const k = b.dataset.l;
    S.langs = S.langs.includes(k) ? S.langs.filter(x => x !== k) : LANGS.map(l => l.k).filter(x => x === k || S.langs.includes(x));
  }
  save(); renderLangs(); renderList();
});

/* ---------- lista ---------- */
function visibleChans(m) {
  return S.langs.filter(k => m.ch[k]?.length).map(k => [k, m.ch[k]]);
}
function matchHTML(m) {
  const T = DATA.teams, h = T[m.h] || { n: "?" }, a = T[m.a] || { n: "?" };
  const t = now(), len = (SPORT[m.s]?.d || 115) * 60;
  const live = t >= m.t && t < m.t + len, done = t >= m.t + len;
  const vc = visibleChans(m);
  const chans = vc.length
    ? vc.map(([k, cs]) => `<span class="chip"><b>${LANG[k].f}</b>${esc(cs.slice(0, 3).join(" · "))}${cs.length > 3 ? ` +${cs.length - 3}` : ""}</span>`).join("")
    : `<span class="nochan">Sin canal en tus idiomas</span>`;
  return `<button class="m${done ? " done" : ""}" data-m="${esc(m.id)}">
    <div class="time${live ? " live" : ""}">${live ? "EN VIVO" : fmtTime(m.t)}</div>
    <div class="teams">${m.e ? `<div class="team ev"><span>${esc(m.e)}</span></div>` : `
      <div class="team${isFavTeam(m.h) ? " fav" : ""}"><img src="${LOGO(h.l)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'"><span>${esc(h.n)}</span></div>
      <div class="team${isFavTeam(m.a) ? " fav" : ""}"><img src="${LOGO(a.l)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'"><span>${esc(a.n)}</span></div>`}
      ${m.r ? `<div class="rnd">${esc(m.r)}</div>` : ""}
    </div>
    <div class="chans">${chans}</div>
  </button>`;
}
function compHTML(key, title, logo, ms) {
  const closed = S.closed.has(key);
  return `<div class="comp${closed ? " closed" : ""}" data-ck="${esc(key)}">
    <button class="comp-h" data-toggle="${esc(key)}">
      ${logo ? `<img src="${LOGO(logo)}" alt="" loading="lazy" onerror="this.style.visibility='hidden'">` : `<span style="width:20px;text-align:center;color:var(--star)">★</span>`}
      <span class="n">${S.sports.length > 1 && key !== "__mine" ? SPORT[sportOf(key)].f + " " : ""}${esc(title)}</span><span class="cnt">${ms.length}</span>
      <svg class="chev" viewBox="0 0 24 24" width="18" height="18"><path fill="currentColor" d="M7 10l5 5 5-5z"/></svg>
    </button>
    ${ms.map(matchHTML).join("")}
  </div>`;
}
function renderList() {
  $("#pane-cur").innerHTML = dayHTML(dayIdx);
  $("#pane-prev").innerHTML = dayIdx > 0 ? dayHTML(dayIdx - 1) : "";
  $("#pane-next").innerHTML = dayIdx < 6 ? dayHTML(dayIdx + 1) : "";
}
function dayHTML(di) {
  if (!S.sports.length) return `<div class="empty"><b>Ningún deporte elegido</b>Toca arriba ⚽ 🏀 🎾 🏍️ 🏎️ para ver sus partidos.</div>`;
  if (!DATA) return `<div class="empty"><b>Cargando…</b></div>`;
  const from = startOfDay(di), to = startOfDay(di + 1);
  const day = DATA.matches.filter(m => m.t >= from && m.t < to);
  const passes = m => !S.onlyTv || visibleChans(m).length > 0 || isFavTeam(m.h) || isFavTeam(m.a);
  const shown = day.filter(passes);

  let html = "";
  const mine = shown.filter(m => isFavTeam(m.h) || isFavTeam(m.a));
  if (mine.length) html += compHTML("__mine", "Mis equipos", null, mine);

  const byComp = new Map();
  for (const m of shown) { if (!byComp.has(m.c)) byComp.set(m.c, []); byComp.get(m.c).push(m); }

  let favHtml = "";
  for (const fc of S.favComps) {
    const ms = byComp.get(fc.id);
    if (ms?.length) favHtml += compHTML(fc.id, DATA.comps[fc.id]?.n || fc.n, DATA.comps[fc.id]?.l || fc.l, ms);
  }
  if (favHtml) html += (mine.length ? `<div class="sec-title">Mis competiciones</div>` : "") + favHtml;

  if (S.showOthers) {
    const others = [...byComp.keys()].filter(c => !isFavComp(c))
      .sort((x, y) => SPORTS.findIndex(z => z.k === sportOf(x)) - SPORTS.findIndex(z => z.k === sportOf(y))
        || (DATA.comps[x]?.o ?? 999) - (DATA.comps[y]?.o ?? 999));
    if (others.length) {
      if (html) html += `<div class="sec-title">Todas las competiciones</div>`;
      for (const c of others) html += compHTML(c, DATA.comps[c]?.n || c, DATA.comps[c]?.l, byComp.get(c));
    }
  }

  if (!html) {
    html = `<div class="empty"><b>No hay partidos</b>${day.length && S.onlyTv
      ? `Hay ${day.length} partidos este día, pero ninguno con canal en los idiomas marcados.`
      : "Prueba otro día."}</div>`;
  }
  return html;
}
$("#list").addEventListener("click", e => {
  const tg = e.target.closest("[data-toggle]");
  if (tg) {
    const k = tg.dataset.toggle;
    S.closed.has(k) ? S.closed.delete(k) : S.closed.add(k);
    document.querySelectorAll(`.comp[data-ck="${CSS.escape(k)}"]`).forEach(c => c.classList.toggle("closed", S.closed.has(k)));
    save(); return;
  }
  const mb = e.target.closest("[data-m]");
  if (mb) openMatch(DATA.matches.find(m => m.id === mb.dataset.m));
});

/* Deslizar para cambiar de día: la lista sigue al dedo y el día contiguo entra por el lado */
const swipe = { x: 0, y: 0, t: 0, dx: 0, mode: null, busy: false };
const track = () => $("#track");
function setTrack(dx, anim) {
  track().style.transition = anim ? "transform .28s cubic-bezier(.2,.8,.2,1)" : "none";
  track().style.transform = dx ? `translate3d(${dx}px,0,0)` : "";
}
$("#list").addEventListener("touchstart", e => {
  if (swipe.busy || e.touches.length > 1) { swipe.mode = "none"; return; }
  Object.assign(swipe, { x: e.touches[0].clientX, y: e.touches[0].clientY, t: Date.now(), dx: 0, mode: null });
  // los paneles laterales se colocan a la altura que se está viendo
  const off = Math.max(0, window.scrollY - $("#list").offsetTop + $("#top").offsetHeight);
  for (const id of ["#pane-prev", "#pane-next"]) $(id).style.top = off + "px";
}, { passive: true });
$("#list").addEventListener("touchmove", e => {
  if (swipe.mode === "none" || swipe.mode === "v") return;
  const dx = e.touches[0].clientX - swipe.x, dy = e.touches[0].clientY - swipe.y;
  if (!swipe.mode) {
    if (Math.abs(dx) < 8 && Math.abs(dy) < 8) return;
    swipe.mode = Math.abs(dx) > Math.abs(dy) ? "h" : "v";
    if (swipe.mode === "v") return;
  }
  e.preventDefault();
  const edge = (dx > 0 && dayIdx === 0) || (dx < 0 && dayIdx === 6);
  swipe.dx = edge ? dx * 0.25 : dx;
  setTrack(swipe.dx, false);
}, { passive: false });
function endSwipe() {
  if (swipe.mode !== "h") { swipe.mode = null; return; }
  swipe.mode = null;
  const W = $("#list").clientWidth, dx = swipe.dx, v = Math.abs(dx) / Math.max(1, Date.now() - swipe.t);
  const dir = dx < 0 ? 1 : -1, n = dayIdx + dir;
  if (n < 0 || n > 6 || (Math.abs(dx) < W * 0.22 && v < 0.45)) { setTrack(0, true); return; }
  swipe.busy = true;
  setTrack(-dir * W, true);
  const done = () => {
    if (!swipe.busy) return;
    track().removeEventListener("transitionend", done);
    dayIdx = n; renderDays(); renderList();
    setTrack(0, false); window.scrollTo({ top: 0 });
    swipe.busy = false;
  };
  track().addEventListener("transitionend", done);
  setTimeout(() => { if (swipe.busy) done(); }, 450);
}
$("#list").addEventListener("touchend", endSwipe, { passive: true });
$("#list").addEventListener("touchcancel", endSwipe, { passive: true });

/* ---------- hojas inferiores ---------- */
function openSheet(html) {
  $("#sheet").innerHTML = `<div class="grip"></div>` + html;
  $("#sheet").classList.remove("hidden"); $("#sheet-bg").classList.remove("hidden");
  $("#sheet").scrollTop = 0;
  document.body.style.overflow = "hidden";
}
function closeSheet() {
  $("#sheet").classList.add("hidden"); $("#sheet-bg").classList.add("hidden");
  document.body.style.overflow = "";
  sheetRender = null;
  renderList();
}
let sheetRender = null;
$("#sheet-bg").addEventListener("click", closeSheet);

/* Cerrar arrastrando la hoja hacia abajo desde arriba */
let sy = null;
$("#sheet").addEventListener("touchstart", e => { sy = $("#sheet").scrollTop <= 0 && !e.target.closest(".handle") ? e.touches[0].clientY : null; }, { passive: true });
$("#sheet").addEventListener("touchend", e => { if (sy !== null && e.changedTouches[0].clientY - sy > 90) closeSheet(); sy = null; }, { passive: true });

/* Catálogo de todos los equipos/jugadores y competiciones (aunque no jueguen esta semana) */
const CAT = {};
async function loadCats() {
  await Promise.all(SPORTS.map(async x => {
    if (CAT[x.k]) return;
    try { const r = await fetch(`cat-${x.k}.json?ts=${Math.floor(Date.now() / 3600000)}`); if (r.ok) CAT[x.k] = await r.json(); } catch {}
  }));
}
const findIn = (kind, id) => DATA?.[kind]?.[id] || Object.values(CAT).map(c => c[kind]?.[id]).find(Boolean);
function searchCat(kind, q, isFav, extra) {
  const seen = new Set(), out = [];
  const add = (id, x, sp) => { if (!seen.has(id) && !isFav(id) && norm(x.n).includes(q)) { seen.add(id); out.push([id, x, sp]); } };
  for (const x of SPORTS) for (const [id, v] of Object.entries(CAT[x.k]?.[kind] || {})) add(id, v, x.k);
  for (const [id, v] of Object.entries(extra || {})) add(id, v, kind === "comps" ? sportOf(id) : "futbol");
  const starts = ([, x]) => norm(x.n).startsWith(q) || norm(x.n).includes(" " + q) ? 0 : 1;
  return out.sort((a, b) => starts(a) - starts(b) || a[1].n.length - b[1].n.length);
}
const sportTag = sp => sp && sp !== "futbol" ? SPORT[sp].f + " " : "";

function toggleTeam(id) {
  if (isFavTeam(id)) S.favTeams = S.favTeams.filter(t => t.id !== id);
  else { const t = findIn("teams", id); S.favTeams.push({ id, n: t?.n || id, l: t?.l || null }); }
  save();
}
function toggleComp(id) {
  if (isFavComp(id)) S.favComps = S.favComps.filter(c => c.id !== id);
  else { const c = findIn("comps", id); S.favComps.push({ id, n: c?.n || id, l: c?.l || null }); }
  save();
}

function openMatch(m) {
  if (!m) return;
  sheetRender = () => {
    const T = DATA.teams, h = T[m.h] || { n: "?" }, a = T[m.a] || { n: "?" }, c = DATA.comps[m.c] || { n: m.c };
    const d = new Date(m.t * 1000).toLocaleString("es-ES", { weekday: "long", day: "numeric", month: "long", hour: "2-digit", minute: "2-digit" });
    const order = [...S.langs, ...LANGS.map(l => l.k).filter(k => !S.langs.includes(k))];
    const langs = order.filter(k => m.ch[k]?.length).map(k =>
      `<div class="sh-lang${S.langs.includes(k) ? "" : " off"}"><h4>${LANG[k].f} ${esc(LANG[k].n)}</h4>
       <div class="chans">${m.ch[k].map(x => `<span class="chip">${esc(x)}</span>`).join("")}</div></div>`).join("")
      || `<p class="nochan">No consta ningún canal para este partido.</p>`;
    const star = on => `<span class="s${on ? " on" : ""}">${on ? "★" : "☆"}</span>`;
    openSheet(`
      <div class="sh-head">
        <div class="c">${esc(c.n)}${m.r ? " · " + esc(m.r) : ""}</div>
        ${m.e ? `<div class="vs"><div><img src="${LOGO(c.l)}" alt="" onerror="this.style.visibility='hidden'">${esc(m.e)}<span class="t">${fmtTime(m.t)}</span></div></div>` : `
        <div class="vs">
          <div><img src="${LOGO(h.l)}" alt="" onerror="this.style.visibility='hidden'">${esc(h.n)}</div>
          <span class="t">${fmtTime(m.t)}</span>
          <div><img src="${LOGO(a.l)}" alt="" onerror="this.style.visibility='hidden'">${esc(a.n)}</div>
        </div>`}
        <div class="c" style="text-transform:capitalize">${esc(d)}</div>
      </div>
      ${langs}
      <div class="btns">${m.e ? "" : `
        <button class="btn" data-ft="${esc(m.h)}"><img src="${LOGO(h.l)}" alt="" onerror="this.style.visibility='hidden'">Seguir a ${esc(h.n)}${star(isFavTeam(m.h))}</button>
        <button class="btn" data-ft="${esc(m.a)}"><img src="${LOGO(a.l)}" alt="" onerror="this.style.visibility='hidden'">Seguir a ${esc(a.n)}${star(isFavTeam(m.a))}</button>`}
        <button class="btn" data-fc="${esc(m.c)}"><img src="${LOGO(c.l)}" alt="" onerror="this.style.visibility='hidden'">Competición favorita: ${esc(c.n)}${star(isFavComp(m.c))}</button>
      </div>`);
  };
  sheetRender();
}

let favTab = "teams", favQuery = "";
function favBody() {
    const q = norm(favQuery.trim());
    let body = "";
    if (favTab === "teams") {
      body += S.favTeams.length
        ? S.favTeams.map(t => `<div class="row"><img src="${LOGO(DATA?.teams[t.id]?.l || t.l)}" alt="" onerror="this.style.visibility='hidden'"><span class="n">${esc(t.n)}</span><button class="act star" data-ft="${esc(t.id)}">★</button></div>`).join("")
        : `<p class="hint">Aún no sigues a ningún equipo. Búscalo abajo o tócalo en cualquier partido.</p>`;
      if (q.length >= 2) {
        const res = searchCat("teams", q, isFavTeam, DATA?.teams).slice(0, 40);
        body += `<p class="hint">Resultados${Object.keys(CAT).length < SPORTS.length ? " (cargando catálogo…)" : ""}</p>` +
          (res.map(([id, t, sp]) => `<div class="row"><img src="${LOGO(t.l)}" alt="" onerror="this.style.visibility='hidden'"><span class="n">${sportTag(sp)}${esc(t.n)}</span><button class="act" data-ft="${esc(id)}">☆</button></div>`).join("") || `<p class="hint">Nada.</p>`);
      }
    } else {
      body += S.favComps.length
        ? `<p class="hint">Arrastra ☰ para cambiar el orden en que salen.</p><div id="sortable">` +
          S.favComps.map((c, i) => `<div class="row" data-i="${i}"><span class="handle">☰</span><img src="${LOGO(DATA?.comps[c.id]?.l || c.l)}" alt="" onerror="this.style.visibility='hidden'"><span class="n">${sportOf(c.id) !== "futbol" ? SPORT[sportOf(c.id)].f + " " : ""}${esc(DATA?.comps[c.id]?.n || c.n)}</span><button class="act star" data-fc="${esc(c.id)}">★</button></div>`).join("") + `</div>`
        : `<p class="hint">Aún no tienes competiciones favoritas. Búscalas abajo.</p>`;
      body += `<div class="toggle-row">Mostrar también el resto de competiciones<button class="sw${S.showOthers ? " on" : ""}" data-others="1" aria-label="Mostrar el resto"></button></div>`;
      if (q || DATA) {
        const res = q ? searchCat("comps", q, isFavComp, DATA?.comps).slice(0, 60)
          : Object.entries(DATA.comps).filter(([id]) => !isFavComp(id)).sort((x, y) => x[1].o - y[1].o).slice(0, 25);
        body += `<p class="hint">${q ? "Resultados" : "Competiciones con partidos esta semana"}</p>` +
          (res.map(([id, c]) => `<div class="row"><img src="${LOGO(c.l)}" alt="" onerror="this.style.visibility='hidden'"><span class="n">${sportOf(id) !== "futbol" ? SPORT[sportOf(id)].f + " " : ""}${esc(c.n)}</span><button class="act" data-fc="${esc(id)}">☆</button></div>`).join("") || `<p class="hint">Nada.</p>`);
      }
    }
    return body;
}
function openFavs() {
  sheetRender = () => {
    const keep = $("#sheet").classList.contains("hidden") ? 0 : $("#sheet").scrollTop;
    openSheet(`
      <div class="tabs"><button data-tab="teams" class="${favTab === "teams" ? "on" : ""}">Equipos</button><button data-tab="comps" class="${favTab === "comps" ? "on" : ""}">Competiciones</button></div>
      <input class="search" type="search" placeholder="${favTab === "teams" ? "Buscar equipo…" : "Buscar competición…"}" value="${esc(favQuery)}" autocomplete="off" autocorrect="off">
      <div id="fav-body">${favBody()}</div>`);
    $("#sheet").scrollTop = keep;
    setupSort();
  };
  sheetRender();
}
$("#btn-fav").addEventListener("click", () => {
  favQuery = ""; openFavs();
  loadCats().then(() => { migrateFavs(); if ($("#fav-body")) { $("#fav-body").innerHTML = favBody(); setupSort(); } });
});

$("#sheet").addEventListener("click", e => {
  const b = e.target.closest("button"); if (!b) return;
  if (b.dataset.ft) { toggleTeam(b.dataset.ft); sheetRender?.(); }
  else if (b.dataset.fc) { toggleComp(b.dataset.fc); sheetRender?.(); }
  else if (b.dataset.tab) { favTab = b.dataset.tab; favQuery = ""; sheetRender?.(); }
  else if (b.dataset.others) { S.showOthers = !S.showOthers; save(); sheetRender?.(); }
});
$("#sheet").addEventListener("input", e => {
  if (!e.target.classList.contains("search")) return;
  favQuery = e.target.value;
  $("#fav-body").innerHTML = favBody();
  setupSort();
});

/* Reordenar competiciones arrastrando el asa */
function setupSort() {
  const box = $("#sortable"); if (!box) return;
  box.querySelectorAll(".handle").forEach(hd => hd.addEventListener("pointerdown", e => {
    e.preventDefault();
    const row = hd.closest(".row"), rows = [...box.children], from = rows.indexOf(row);
    const h = row.offsetHeight, y0 = e.clientY;
    let to = from;
    row.classList.add("dragging"); hd.setPointerCapture(e.pointerId);
    const move = ev => {
      const dy = ev.clientY - y0;
      row.style.transform = `translateY(${dy}px)`;
      to = Math.max(0, Math.min(rows.length - 1, from + Math.round(dy / h)));
      rows.forEach((r, i) => {
        if (r === row) return;
        const shift = (from < to && i > from && i <= to) ? -h : (from > to && i < from && i >= to) ? h : 0;
        r.style.transition = "transform .15s"; r.style.transform = shift ? `translateY(${shift}px)` : "";
      });
    };
    const up = () => {
      hd.removeEventListener("pointermove", move); hd.removeEventListener("pointerup", up); hd.removeEventListener("pointercancel", up);
      if (to !== from) { const [it] = S.favComps.splice(from, 1); S.favComps.splice(to, 0, it); save(); }
      sheetRender?.();
    };
    hd.addEventListener("pointermove", move); hd.addEventListener("pointerup", up); hd.addEventListener("pointercancel", up);
  }));
}

/* ---------- datos ---------- */
function renderFoot() {
  if (!DATA || !DATA.generated) { $("#foot").textContent = ""; return; }
  const mins = Math.round((now() - DATA.generated) / 60);
  $("#foot").textContent = `Datos de futbolenlatv y webs hermanas · actualizado ${mins < 1 ? "ahora" : mins < 60 ? `hace ${mins} min` : `hace ${Math.round(mins / 60)} h`}`;
}
async function loadSport(k) {
  try {
    const r = await fetch(`data-${k}.json?ts=${Math.floor(Date.now() / 60000)}`, { cache: "no-store" });
    if (!r.ok) throw new Error(r.status);
    SD[k] = await r.json();
    try { localStorage.setItem("ptv.cache." + k, JSON.stringify(SD[k])); } catch {}
  } catch {
    if (!SD[k]) { try { SD[k] = JSON.parse(localStorage.getItem("ptv.cache." + k)); } catch {} }
  }
}
async function load() {
  await Promise.all(S.sports.map(loadSport));
  mergeData(); renderList(); renderFoot();
}

renderDays(); renderSports(); renderLangs();
try { localStorage.removeItem("ptv.cache"); } catch {}
for (const k of S.sports) { try { SD[k] = JSON.parse(localStorage.getItem("ptv.cache." + k)); } catch {} }
mergeData(); renderList(); renderFoot();
load();
document.addEventListener("visibilitychange", () => {
  if (document.visibilityState === "visible") {
    if (dayIdx === 0) renderDays();
    load();
  }
});
setInterval(() => { if (document.visibilityState === "visible") { renderList(); renderFoot(); } }, 60000);
if ("serviceWorker" in navigator) navigator.serviceWorker.register("sw.js").catch(() => {});
