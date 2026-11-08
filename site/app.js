"use strict";

const $ = (s) => document.querySelector(s);
const $$ = (s) => [...document.querySelectorAll(s)];
const won = (n) => (typeof n === "number" ? n.toLocaleString("ko-KR") + "원" : "");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const PAGE = 40;
const HOT_PAGE = 6;
const DAY = 86400000;
const STORES = ["all", "playstation", "nintendo"];
const BASE_TYPES = ["", "게임", "에디션", "번들"];

const state = { store: "all", kind: "all", shown: PAGE, hotShown: HOT_PAGE, data: { hot: null, games: null, news: null } };
const toggles = { big: true, lowest: false, base: false, noplus: false, vr: false };

// 발매 시기. 닌텐도는 발매일이 있고, PS 는 스토어 표시(방금 출시·출시 예정)만 있다
const AGES = {
  all: [["all", "발매 시기 전체", () => true]],
  nintendo: [
    ["all", "발매 시기 전체", () => true],
    ["y1", "최근 1년 발매", (d) => d.released && ageDays(d) >= 0 && ageDays(d) <= 365],
    ["y3", "1~3년 전 발매", (d) => d.released && ageDays(d) > 365 && ageDays(d) <= 365 * 3],
    ["old", "3년 넘은 게임", (d) => d.released && ageDays(d) > 365 * 3],
    ["soon", "발매 예정", (d) => d.released && ageDays(d) < 0],
  ],
  playstation: [
    ["all", "발매 시기 전체", () => true],
    ["new", "방금 출시 (30일)", (d) => d.fresh === "new"],
    ["soon", "출시 예정·예약", (d) => d.fresh === "upcoming"],
  ],
};

function ageDays(d) { return Math.floor((Date.now() - new Date(d.released + "T00:00:00+09:00")) / DAY); }
function ago(iso) {
  if (!iso) return "";
  const m = Math.round((Date.now() - new Date(iso)) / 60000);
  if (m < 60) return `${Math.max(m, 1)}분 전`;
  if (m < 60 * 24) return `${Math.round(m / 60)}시간 전`;
  return `${Math.round(m / 1440)}일 전`;
}
function daysLeft(iso) { return Math.ceil((new Date(iso) - Date.now()) / DAY); }
function endText(iso) {
  const d = new Date(iso);
  const left = daysLeft(iso);
  return left <= 1 ? "오늘·내일 마감" : `~${d.getMonth() + 1}/${d.getDate()}`;
}

async function load(name) {
  try {
    const r = await fetch(`${name}.json?t=${Date.now()}`, { cache: "no-store" });
    return r.ok ? await r.json() : null;
  } catch { return null; }
}

function games(store = state.store) {
  const g = state.data.games || {};
  if (store === "all") return [...(g.playstation || []), ...(g.nintendo || [])];
  return g[store] || [];
}

/* ---------- 같은 게임의 기종별 버전 합치기 ---------- */
// PS 는 PS4판·PS5판이, 닌텐도는 스위치판·스위치2판이 따로 올라온다. 이름·종류가 같으면 카드 하나로 합치고
// 가장 싼 버전을 대표로 보여 준다 (기종 필터를 고르면 그 기종 버전만 남긴 뒤 합친다).
// 스토어가 다르면(PS판·스위치판) 합치지 않는다
const norm = (s) => s.toLowerCase().replace(/[\s:：\-–—'’!?.,()[\]™®]/g, "");
const union = (vs, f) => [...new Set(vs.flatMap((v) => v[f] || []))];
const minOf = (vs, f) => { const xs = vs.map((v) => v[f]).filter((x) => x != null); return xs.length ? Math.min(...xs) : undefined; };

function group(items) {
  const m = new Map();
  for (const d of items) {
    const k = `${d.store}|${norm(d.name)}|${d.plus ? 1 : 0}`;  // PS판과 스위치판은 따로 둔다
    (m.get(k) || m.set(k, []).get(k)).push(d);
  }
  return [...m.values()].map((vs) => {
    if (vs.length === 1) return vs[0];
    vs.sort((a, b) => a.price - b.price);
    const best = vs[0];
    return {
      ...best, versions: vs,
      platforms: union(vs, "platforms").sort((a, b) => b.localeCompare(a, "en", { numeric: true })),
      genres: union(vs, "genres"), vr: union(vs, "vr"),
      discount: Math.max(...vs.map((v) => v.discount)),
      regular: Math.max(...vs.map((v) => v.regular)),
      pop: minOf(vs, "pop"), rel: minOf(vs, "rel"),
      new_low: vs.some((v) => v.new_low), at_low: vs.some((v) => v.at_low), wish: vs.some((v) => v.wish),
      fresh: vs.find((v) => v.fresh)?.fresh,
      released: vs.map((v) => v.released).filter(Boolean).sort()[0],
      ends: vs.map((v) => v.ends).filter(Boolean).sort()[0],
    };
  });
}

/* ---------- 카드 ---------- */

function card(d, rank) {
  const ps = d.store === "playstation";
  const cls = ps ? "ps" : "ns";
  const plat = (d.platforms || []).join("·") || (ps ? "PS" : "Switch");
  const img = d.img
    ? `<img class="bg" src="${esc(d.img)}" alt="" loading="lazy" referrerpolicy="no-referrer" aria-hidden="true">
       <img class="fg" src="${esc(d.img)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.parentNode.querySelectorAll('img').forEach(i=>i.remove())">`
    : "";
  const flag = d.new_low ? `<span class="flag">새 최저가</span>` : d.at_low ? `<span class="flag">최저가</span>` : "";
  const vs = d.versions || [];
  const spread = vs.length > 1 && vs[vs.length - 1].price > vs[0].price;
  const meta = [];
  if (vs.length > 1) {
    meta.push(spread
      ? vs.map((v) => `${esc((v.platforms || []).join("·") || "?")} ${won(v.price)}`).slice(0, 3).join(" · ")
      : `${vs.length}개 기종 같은 가격`);
  }
  if (d.pop && d.pop <= 100 && rank == null) meta.push(`<span class="hot">인기 ${d.pop}위</span>`);
  if (d.wish) meta.push(`<span class="wish">위시리스트</span>`);
  if (d.fresh === "new") meta.push("방금 출시");
  if (d.fresh === "upcoming") meta.push("출시 예정");
  if (d.type && d.type !== "게임") meta.push(esc(d.type));
  if (d.plus) meta.push("PS Plus 전용");
  if ((d.vr || []).length) meta.push(esc(d.vr.join("·")));
  if (d.released) meta.push(`${d.released.slice(0, 4)}년 발매`);
  if (d.ends) meta.push(endText(d.ends));
  return `<li><a class="card" href="${esc(d.url)}" target="_blank" rel="noopener">
    <div class="art ${cls}">${img}<span class="tag ${cls}">${esc(plat)}</span>${flag}${rank != null ? `<span class="rank">${rank}</span>` : ""}</div>
    <div class="body">
      <div class="name">${esc(d.name)}</div>
      <div class="pct">-${d.discount}%</div>
      <div class="now">${won(d.price)}${spread ? "~" : ""}</div>
      <div class="was">${won(d.regular)}</div>
      ${meta.length ? `<div class="meta">${meta.map((m) => m.startsWith("<") ? m : `<span>${m}</span>`).join("")}</div>` : ""}
    </div></a></li>`;
}

/* ---------- 위쪽: 오늘의 할인 · PS 인기 TOP 10 · 곧 끝나는 닌텐도 할인 · 새 최저가 ---------- */

function renderStats() {
  const list = group(games());
  const today = list.filter((d) => d.ends && daysLeft(d.ends) <= 1).length;
  const lows = list.filter((d) => d.new_low).length;
  const half = list.filter((d) => d.discount >= 50).length;
  const stats = [["할인 중인 게임", list.length], ["50% 이상", half]];
  if (state.store !== "playstation") stats.push(["오늘·내일 마감", today]);
  stats.push(["새 최저가", lows]);
  $("#stats").innerHTML = stats.map(([k, v]) => `<span class="stat">${k}<b>${v.toLocaleString()}</b></span>`).join("");
}

function psTop() {
  return group(games("playstation").filter((d) => d.pop && !d.plus && BASE_TYPES.includes(d.type ?? "")))
    .sort((a, b) => a.pop - b.pop).slice(0, 10);
}

function nsEnding() {
  return group(games("nintendo").filter((d) => d.regular >= 30000 && d.discount >= 50 && d.ends
    && daysLeft(d.ends) >= 0 && daysLeft(d.ends) <= 7))
    .sort((a, b) => new Date(a.ends) - new Date(b.ends) || (b.regular - b.price) - (a.regular - a.price)).slice(0, 12);
}

function renderTop() {
  renderStats();
  const s = state.store;
  const top = s === "nintendo" ? [] : psTop();
  $("#ps-top-block").hidden = !top.length;
  $("#ps-top").innerHTML = top.map((d, i) => card(d, i + 1)).join("");
  const ending = s === "playstation" ? [] : nsEnding();
  $("#ns-end-block").hidden = !ending.length;
  $("#ns-end").innerHTML = ending.map((d) => card(d)).join("");
  const lows = group(games().filter((d) => d.new_low))
    .sort((a, b) => (b.prev_low - b.price) - (a.prev_low - a.price)).slice(0, 12);
  $("#lows-block").hidden = !lows.length;
  $("#lows").innerHTML = lows.map((d) => card(d)).join("");
}

/* ---------- 핫딜 · 소식 (전체에서만) ---------- */

function renderHot() {
  const items = (state.data.hot?.items || []).filter((d) => state.kind === "all" || d.kind === state.kind);
  $("#hot-list").innerHTML = items.length ? items.slice(0, state.hotShown).map((d) => `
    <li><a href="${esc(d.url)}" target="_blank" rel="noopener">
      <div class="t">${esc(d.title)}</div>
      <div class="sub"><span class="src">${esc(d.source)}</span>
        <span>${d.kind === "device" ? "기기·주변기기" : "게임"}</span>
        ${d.price ? `<span class="price">${won(d.price)}</span>` : ""}
        <span>${ago(d.posted || d.first_seen)}</span></div>
    </a></li>`).join("") : `<li class="empty">최근 7일 동안 모인 핫딜이 없습니다</li>`;
  $("#hot-more").hidden = items.length <= state.hotShown;
}

function renderNews() {
  const items = state.data.news?.items || [];
  $("#news-list").innerHTML = items.map((d) => `
    <li><a href="${esc(d.url)}" target="_blank" rel="noopener">
      <div class="t">${esc(d.title)}</div>
      <div class="sub"><span class="src">${esc(d.source)}</span><span>${d.posted ? ago(d.posted) : ""}</span></div>
    </a></li>`).join("");
  return items.length;
}

/* ---------- 모든 할인 (고르기) ---------- */

function fillSelects() {
  const all = games();
  const count = (key) => {
    const c = new Map();
    all.forEach((d) => (d[key] || []).forEach((v) => c.set(v, (c.get(v) || 0) + 1)));
    return [...c.entries()].sort((a, b) => b[1] - a[1]);
  };
  const plats = count("platforms").sort((a, b) => b[0].localeCompare(a[0], "en", { numeric: true }));
  $("#platform").innerHTML = `<option value="">기종 전체</option>`
    + plats.map(([v, n]) => `<option value="${esc(v)}">${esc(v)} (${n.toLocaleString()})</option>`).join("");
  $("#genre").innerHTML = `<option value="">장르 전체</option>`
    + count("genres").map(([v, n]) => `<option value="${esc(v)}">${esc(v)} (${n.toLocaleString()})</option>`).join("");
  $("#age").innerHTML = AGES[state.store].map(([k, label]) => `<option value="${k}">${label}</option>`).join("");
  $("#age").hidden = state.store === "all";
}

function filtered() {
  const q = $("#q").value.trim().toLowerCase().replace(/\s+/g, "");
  const min = +$("#mindisc").value;
  const plat = $("#platform").value;
  const genre = $("#genre").value;
  const age = (AGES[state.store].find(([k]) => k === $("#age").value) || AGES[state.store][0])[2];
  const items = group(games().filter((d) => {
    const ps = d.store === "playstation";
    return d.discount >= min
      && (!plat || (d.platforms || []).includes(plat))
      && (!genre || (d.genres || []).includes(genre))
      && age(d)
      && (!toggles.big || d.regular >= 20000)
      && (!toggles.lowest || d.new_low || d.at_low)
      && (!ps || !toggles.base || BASE_TYPES.includes(d.type ?? ""))
      && (!ps || !toggles.noplus || !d.plus)
      && (!toggles.vr || (d.vr || []).length)
      && (!q || d.name.toLowerCase().replace(/\s+/g, "").includes(q));
  }));
  const relKey = (d) => (d.store === "playstation" ? d.rel ?? 1e9 : d.released ? -new Date(d.released).getTime() / DAY : 1e9);
  const key = {
    save: (d) => -(d.regular - d.price),
    pop: (d) => d.pop ?? 1e9,
    disc: (d) => -d.discount * 1e7 - d.regular,
    low: (d) => d.price,
    new: relKey,
    old: (d) => { const k = relKey(d); return k >= 1e9 ? 1e9 : -k; },
    end: (d) => (d.ends ? new Date(d.ends).getTime() : 9e15),
  }[$("#sort").value] || (() => 0);
  return items.sort((a, b) => key(a) - key(b));
}

function renderBrowse() {
  const s = state.store;
  $$(".ps-only").forEach((el) => (el.hidden = s === "nintendo"));
  $$(".ns-only").forEach((el) => (el.hidden = s === "playstation"));
  if ($("#sort").selectedOptions[0]?.hidden) $("#sort").value = "save";
  const failed = (state.data.games?.errors || []).filter((e) => s === "all" || e === (s === "playstation" ? "PlayStation" : "닌텐도"));
  const items = filtered();
  $("#count").textContent = (failed.length ? `이번 수집 실패: ${failed.join(", ")} · ` : "") + `${items.length.toLocaleString()}개`;
  $("#game-list").innerHTML = items.length ? items.slice(0, state.shown).map((d) => card(d)).join("") : `<li class="empty">조건에 맞는 게임이 없습니다</li>`;
  $("#more").hidden = items.length <= state.shown;
}

/* ---------- 전체 ---------- */

function renderMeta() {
  const { hot, games: g } = state.data;
  const t = g?.updated || hot?.updated;
  const errs = [...(g?.errors || []), ...((hot?.errors || []).map((e) => `핫딜 ${e}`))];
  $("#meta").innerHTML = t
    ? `${new Date(t).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })} 수집 (${ago(t)})`
      + (errs.length ? ` · <span class="bad">실패: ${esc(errs.join(", "))}</span>` : "")
    : "데이터를 불러오지 못했습니다";
}

function show(store, scrollTo) {
  state.store = STORES.includes(store) ? store : "all";
  state.shown = PAGE;
  $$(".pills button").forEach((b) => b.setAttribute("aria-selected", b.dataset.store === state.store));
  const all = state.store === "all";
  $("#hot-block").hidden = !all;
  $("#news-block").hidden = !all || !renderNews();
  fillSelects();
  renderTop();
  renderBrowse();
  try { localStorage.setItem("store", state.store); } catch {}
  history.replaceState(null, "", `#${state.store}`);
  if (scrollTo) document.getElementById(scrollTo)?.scrollIntoView();
}

function bind() {
  $$(".pills button").forEach((b) => b.addEventListener("click", () => show(b.dataset.store)));
  $$('[data-group="kind"] button').forEach((b) => b.addEventListener("click", () => {
    $$('[data-group="kind"] button').forEach((x) => x.classList.toggle("on", x === b));
    state.kind = b.dataset.v;
    state.hotShown = HOT_PAGE;
    renderHot();
  }));
  $("#hot-more").addEventListener("click", () => { state.hotShown += 20; renderHot(); });
  $$(".toggles button").forEach((b) => b.addEventListener("click", () => {
    toggles[b.dataset.t] = !toggles[b.dataset.t];
    b.classList.toggle("on", toggles[b.dataset.t]);
    state.shown = PAGE;
    renderBrowse();
  }));
  let timer;
  $("#q").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { state.shown = PAGE; renderBrowse(); }, 150); });
  ["#sort", "#mindisc", "#platform", "#genre", "#age"].forEach((s) => $(s).addEventListener("change", () => { state.shown = PAGE; renderBrowse(); }));
  $("#more").addEventListener("click", () => { state.shown += PAGE; renderBrowse(); });
  window.addEventListener("hashchange", () => route());
}

// 예전 주소(#hot · #news)도 받는다
function route() {
  const h = location.hash.slice(1);
  if (h === "hot") return show("all", "hot-block");
  if (h === "news") return show("all", "news-block");
  if (STORES.includes(h)) return show(h);
  let saved = "all";
  try { saved = localStorage.getItem("store") || "all"; } catch {}
  show(saved);
}

(async function main() {
  bind();
  const [hot, g, news] = await Promise.all([load("hotdeals"), load("games"), load("news")]);
  state.data = { hot, games: g, news };
  renderMeta();
  renderHot();
  route();
})();
