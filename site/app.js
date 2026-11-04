"use strict";

const $ = (s) => document.querySelector(s);
const won = (n) => (typeof n === "number" ? n.toLocaleString("ko-KR") + "원" : "");
const esc = (s) => String(s ?? "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
const PAGE = 60;

const state = { tab: "hot", kind: "all", store: "nintendo", shown: PAGE, data: { hot: null, games: null, news: null } };
const toggles = { big: true, lowest: false, base: false, noplus: false };

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
  const days = Math.ceil((d - Date.now()) / 86400000);
  const md = `${d.getMonth() + 1}/${d.getDate()}`;
  return days <= 1 ? `오늘·내일 마감 (${md})` : `~${md} (${days}일 남음)`;
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

function gameItems() {
  const all = state.data.games?.[state.store] || [];
  const q = $("#q").value.trim().toLowerCase().replace(/\s+/g, "");
  const min = +$("#mindisc").value;
  const ps = state.store === "playstation";
  let items = all.filter((d) =>
    d.discount >= min
    && (!toggles.big || d.regular >= 20000)
    && (!toggles.lowest || d.new_low || d.at_low)
    && (!ps || !toggles.base || ["게임", "에디션", "번들"].includes(d.type))
    && (!ps || !toggles.noplus || !d.plus)
    && (!q || d.name.toLowerCase().replace(/\s+/g, "").includes(q)));
  const sort = $("#sort").value;
  const key = {
    save: (d) => -(d.regular - d.price),
    disc: (d) => -d.discount * 1e7 - d.regular,
    low: (d) => d.price,
    end: (d) => (d.ends ? new Date(d.ends).getTime() : 9e15),
  }[sort];
  items.sort((a, b) => key(a) - key(b));
  return items;
}

function renderGames() {
  const ps = state.store === "playstation";
  document.querySelectorAll(".ps-only").forEach((b) => (b.hidden = !ps));
  $("#sort option[value=end]").hidden = ps;
  if (ps && $("#sort").value === "end") $("#sort").value = "save";
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
        <div class="sub">
          <span class="badge ${ps ? "ps" : "ns"}">${esc((d.platforms || []).join("·") || (ps ? "PS" : "Switch"))}</span>
          ${d.type && d.type !== "게임" ? `<span>${esc(d.type)}</span>` : ""}
          ${d.wish ? `<span class="badge wish">위시리스트</span>` : ""}
          ${d.new_low ? `<span class="badge low">새 최저가 (이전 ${won(d.prev_low)})</span>` : d.at_low ? `<span class="badge low">최저가와 같음</span>` : ""}
          ${d.plus ? `<span>PS Plus 전용</span>` : ""}
          ${d.ends ? `<span>${endText(d.ends)}</span>` : ""}
        </div>
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
    state.store = tab;
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
  ["#sort", "#mindisc"].forEach((s) => $(s).addEventListener("change", () => { state.shown = PAGE; renderGames(); }));
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
