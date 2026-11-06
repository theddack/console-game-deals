"use strict";

const $ = (s) => document.querySelector(s);
const won = (n) => (typeof n === "number" ? n.toLocaleString("ko-KR") + "원" : "");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const PAGE = 60;
const DAY = 86400000;

const state = { tab: "hot", kind: "all", store: "nintendo", shown: PAGE, data: { hot: null, games: null, news: null } };
const toggles = { big: true, lowest: false, base: false, noplus: false, vr: false };

// 발매 시기 고르기. 닌텐도는 발매일이 있고, PS 는 스토어 표시(방금 출시·출시 예정)만 있다
const AGES = {
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
function endText(iso) {
  if (!iso) return "";
  const d = new Date(iso);
  const days = Math.ceil((d - Date.now()) / DAY);
  const md = `${d.getMonth() + 1}/${d.getDate()}`;
  return days <= 1 ? `오늘·내일 마감 (${md})` : `~${md} (${days}일 남음)`;
}
function relText(iso) {
  const [y, m, d] = iso.split("-").map(Number);
  return `${y}.${m}.${d} 발매`;
}

async function load(name) {
  try {
    const r = await fetch(`${name}.json?t=${Date.now()}`, { cache: "no-store" });
    return r.ok ? await r.json() : null;
  } catch { return null; }
}

function renderMeta() {
  const { hot, games } = state.data;
  const t = games?.updated || hot?.updated;
  const errs = [...(games?.errors || []), ...((hot?.errors || []).map((e) => `핫딜 ${e}`))];
  $("#meta").innerHTML = t
    ? `마지막 수집 ${new Date(t).toLocaleString("ko-KR", { month: "numeric", day: "numeric", hour: "2-digit", minute: "2-digit" })} (${ago(t)})`
      + (errs.length ? ` · <span class="bad">실패: ${esc(errs.join(", "))}</span>` : "")
    : "데이터를 불러오지 못했습니다";
}

function renderHot() {
  const items = (state.data.hot?.items || []).filter((d) => state.kind === "all" || d.kind === state.kind);
  $("#hot-list").innerHTML = items.length ? items.map((d) => `
    <li><a class="item" href="${esc(d.url)}" target="_blank" rel="noopener">
      <div class="t">${esc(d.title)}</div>
      <div class="sub"><span class="badge">${esc(d.source)}</span>
        <span>${d.kind === "device" ? "기기·주변기기" : "게임"}</span>
        ${d.price ? `<span>${won(d.price)}</span>` : ""}
        <span>${ago(d.posted || d.first_seen)}</span></div>
    </a></li>`).join("") : `<li class="empty">최근 7일 동안 모인 핫딜이 없습니다</li>`;
}

// 스토어가 바뀔 때 기종·장르·발매 시기 목록을 그 스토어 데이터로 다시 채운다
function fillSelects() {
  const all = state.data.games?.[state.store] || [];
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
}

function gameItems() {
  const all = state.data.games?.[state.store] || [];
  const q = $("#q").value.trim().toLowerCase().replace(/\s+/g, "");
  const min = +$("#mindisc").value;
  const plat = $("#platform").value;
  const genre = $("#genre").value;
  const age = (AGES[state.store].find(([k]) => k === $("#age").value) || AGES[state.store][0])[2];
  const ps = state.store === "playstation";
  const items = all.filter((d) =>
    d.discount >= min
    && (!plat || (d.platforms || []).includes(plat))
    && (!genre || (d.genres || []).includes(genre))
    && age(d)
    && (!toggles.big || d.regular >= 20000)
    && (!toggles.lowest || d.new_low || d.at_low)
    && (!ps || !toggles.base || ["게임", "에디션", "번들"].includes(d.type))
    && (!ps || !toggles.noplus || !d.plus)
    && (!ps || !toggles.vr || (d.vr || []).length)
    && (!q || d.name.toLowerCase().replace(/\s+/g, "").includes(q)));
  const relKey = (d) => (ps ? d.rel ?? 1e9 : d.released ? -new Date(d.released).getTime() / DAY : 1e9);
  const key = {
    save: (d) => -(d.regular - d.price),
    pop: (d) => d.pop ?? 1e9,
    disc: (d) => -d.discount * 1e7 - d.regular,
    low: (d) => d.price,
    new: relKey,
    old: (d) => { const k = relKey(d); return k >= 1e9 ? 1e9 : -k; },
    end: (d) => (d.ends ? new Date(d.ends).getTime() : 9e15),
  }[$("#sort").value] || ((d) => 0);
  items.sort((a, b) => key(a) - key(b));
  return items;
}

function badges(d, ps) {
  const out = [`<span class="badge ${ps ? "ps" : "ns"}">${esc((d.platforms || []).join("·") || (ps ? "PS" : "Switch"))}</span>`];
  if (d.type && d.type !== "게임") out.push(`<span>${esc(d.type)}</span>`);
  if (d.fresh === "new") out.push(`<span class="badge new">방금 출시</span>`);
  if (d.fresh === "upcoming") out.push(`<span class="badge new">출시 예정</span>`);
  if (d.wish) out.push(`<span class="badge wish">위시리스트</span>`);
  if (d.new_low) out.push(`<span class="badge low">새 최저가 (이전 ${won(d.prev_low)})</span>`);
  else if (d.at_low) out.push(`<span class="badge low">최저가와 같음</span>`);
  if (d.pop && d.pop <= 100) out.push(`<span class="badge pop">인기 ${d.pop}위</span>`);
  if ((d.vr || []).length) out.push(`<span>${esc(d.vr.join("·"))}</span>`);
  if (d.plus) out.push(`<span>PS Plus 전용</span>`);
  if ((d.genres || []).length) out.push(`<span>${esc(d.genres.slice(0, 2).join("·"))}</span>`);
  if (d.released) out.push(`<span>${relText(d.released)}</span>`);
  if (d.ends) out.push(`<span>${endText(d.ends)}</span>`);
  return out.join("");
}

function renderGames() {
  const ps = state.store === "playstation";
  document.querySelectorAll(".ps-only").forEach((b) => (b.hidden = !ps));
  document.querySelectorAll(".ns-only").forEach((b) => (b.hidden = ps));
  const sort = $("#sort");
  if (sort.selectedOptions[0]?.hidden) sort.value = "save";
  const failed = state.data.games?.errors?.includes(ps ? "PlayStation" : "닌텐도");
  const items = gameItems();
  $("#count").textContent = failed
    ? "이번 수집에서 이 스토어를 가져오지 못했습니다. 다음 수집 때 다시 시도합니다"
    : `조건에 맞는 할인 ${items.length.toLocaleString()}개`;
  $("#game-list").innerHTML = items.length ? items.slice(0, state.shown).map((d) => `
    <li><a class="item" href="${esc(d.url)}" target="_blank" rel="noopener">
      <div class="thumb">${d.img ? `<img src="${esc(d.img)}" alt="" loading="lazy" referrerpolicy="no-referrer" onerror="this.remove()">` : ""}</div>
      <div>
        <div class="t">${esc(d.name)}</div>
        <div class="sub">${badges(d, ps)}</div>
      </div>
      <div class="price"><span class="pct">-${d.discount}%</span><span class="now">${won(d.price)}</span>
        <span class="was">${won(d.regular)}</span></div>
    </a></li>`).join("") : `<li class="empty">조건에 맞는 게임이 없습니다</li>`;
  $("#more").hidden = items.length <= state.shown;
}

function renderNews() {
  const items = state.data.news?.items || [];
  $("#news-list").innerHTML = items.length ? items.map((d) => `
    <li><a class="item" href="${esc(d.url)}" target="_blank" rel="noopener">
      <div class="t">${esc(d.title)}</div>
      <div class="sub"><span class="badge">${esc(d.source)}</span><span>${d.posted ? ago(d.posted) : ""}</span></div>
    </a></li>`).join("") : `<li class="empty">최근 세일 소식이 없습니다</li>`;
}

function show(tab) {
  state.tab = tab;
  document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", b.dataset.tab === tab));
  $("#tab-hot").hidden = tab !== "hot";
  $("#tab-news").hidden = tab !== "news";
  $("#tab-games").hidden = !(tab === "nintendo" || tab === "playstation");
  if (tab === "nintendo" || tab === "playstation") {
    if (state.store !== tab || !$("#age").options.length) {
      state.store = tab;
      fillSelects();
    }
    state.shown = PAGE;
    renderGames();
  }
  try { localStorage.setItem("tab", tab); } catch {}
  history.replaceState(null, "", `#${tab}`);
}

function bind() {
  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => show(b.dataset.tab)));
  document.querySelectorAll('[data-group="kind"] button').forEach((b) => b.addEventListener("click", () => {
    document.querySelectorAll('[data-group="kind"] button').forEach((x) => x.classList.toggle("on", x === b));
    state.kind = b.dataset.v;
    renderHot();
  }));
  document.querySelectorAll(".toggles button").forEach((b) => b.addEventListener("click", () => {
    toggles[b.dataset.t] = !toggles[b.dataset.t];
    b.classList.toggle("on", toggles[b.dataset.t]);
    state.shown = PAGE;
    renderGames();
  }));
  let timer;
  $("#q").addEventListener("input", () => { clearTimeout(timer); timer = setTimeout(() => { state.shown = PAGE; renderGames(); }, 150); });
  ["#sort", "#mindisc", "#platform", "#genre", "#age"].forEach((s) => $(s).addEventListener("change", () => { state.shown = PAGE; renderGames(); }));
  $("#more").addEventListener("click", () => { state.shown += PAGE; renderGames(); });
  window.addEventListener("hashchange", () => {
    const t = location.hash.slice(1);
    if (t !== state.tab && ["hot", "nintendo", "playstation", "news"].includes(t)) show(t);
  });
}

(async function main() {
  bind();
  let tab = location.hash.slice(1);
  if (!["hot", "nintendo", "playstation", "news"].includes(tab)) {
    try { tab = localStorage.getItem("tab") || "hot"; } catch { tab = "hot"; }
  }
  const [hot, games, news] = await Promise.all([load("hotdeals"), load("games"), load("news")]);
  state.data = { hot, games, news };
  renderMeta();
  renderHot();
  renderNews();
  show(tab);
})();
