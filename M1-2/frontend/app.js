const API = (window.API_BASE_URL || "").replace(/\/$/, "");
const PAGE = 20;
const $ = (id) => document.getElementById(id);
let convId = null;   // 현재 대화 (null = 새 대화)
let offset = 0;
let total = 0;

// ---- API 호출 (콜드스타트 안내 + 오류 표시) ----
async function api(path, { blob = false, ...options } = {}) {
  const wake = setTimeout(() => ($("wake").hidden = false), 3000);
  try {
    const res = await fetch(API + path, {
      headers: { "Content-Type": "application/json" }, ...options,
    });
    if (!res.ok) {
      let detail = res.statusText;
      try {
        const body = await res.json();
        detail = typeof body.detail === "string" ? body.detail : "입력값을 확인해 주세요.";
      } catch (_) {}
      throw new Error(detail);
    }
    $("error").hidden = true;
    if (blob) return res.blob();
    return res.status === 204 ? null : res.json();
  } catch (e) {
    showError(e.message === "Failed to fetch" ? "서버에 연결할 수 없습니다." : e.message);
    throw e;
  } finally {
    clearTimeout(wake);
    $("wake").hidden = true;
  }
}

function showError(msg) { $("error").textContent = msg; $("error").hidden = false; }

function el(tag, text, cls) {
  const n = document.createElement(tag);
  if (text !== undefined) n.textContent = text;   // textContent 만 사용 (XSS 방지)
  if (cls) n.className = cls;
  return n;
}

// ---- 탭 ----
document.querySelectorAll(".tab").forEach((b) => b.addEventListener("click", () => {
  document.querySelectorAll(".tab").forEach((t) => t.classList.toggle("active", t === b));
  ["chat", "data", "history"].forEach((n) => ($("tab-" + n).hidden = n !== b.dataset.tab));
  if (b.dataset.tab === "data") loadData();
  if (b.dataset.tab === "history") loadConversations();
}));

// ---- 다크 모드 ----
function applyTheme(theme) {
  document.documentElement.dataset.theme = theme;
  localStorage.setItem("theme", theme);
  $("theme-toggle").textContent = theme === "dark" ? "☀️" : "🌙";
}
$("theme-toggle").addEventListener("click", () => {
  applyTheme(document.documentElement.dataset.theme === "dark" ? "light" : "dark");
});
applyTheme(document.documentElement.dataset.theme);

// ---- 연평균 추이 그래프 (SVG, 라이브러리 없음) ----
const SVG = "http://www.w3.org/2000/svg";
function svgEl(tag, attrs, text) {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs)) n.setAttribute(k, v);
  if (text !== undefined) n.textContent = text;
  return n;
}
function drawChart(yearly) {
  const svg = $("chart");
  svg.replaceChildren();
  if (yearly.length < 2) { $("chart-note").textContent = "그래프를 그리기엔 데이터가 부족합니다."; return; }
  const W = 760, H = 230, L = 48, R = 14, T = 12, B = 28;
  const means = yearly.map((y) => y.mean);
  const lo = Math.floor(Math.min(...means) / 10) * 10, hi = Math.ceil(Math.max(...means) / 10) * 10;
  const y0 = yearly[0].year, y1 = yearly[yearly.length - 1].year;
  const x = (yr) => L + ((yr - y0) / Math.max(1, y1 - y0)) * (W - L - R);
  const y = (v) => T + (1 - (v - lo) / (hi - lo)) * (H - T - B);
  for (let v = lo; v <= hi; v += (hi - lo) / 4) {
    svg.append(svgEl("line", { class: "grid", x1: L, x2: W - R, y1: y(v), y2: y(v) }));
    svg.append(svgEl("text", { class: "axis", x: L - 6, y: y(v) + 4, "text-anchor": "end" }, Math.round(v)));
  }
  for (let yr = Math.ceil(y0 / 10) * 10; yr <= y1; yr += 10) {
    svg.append(svgEl("text", { class: "axis", x: x(yr), y: H - 8, "text-anchor": "middle" }, yr));
  }
  svg.append(svgEl("polyline", { class: "line", points: yearly.map((p) => x(p.year) + "," + y(p.mean)).join(" ") }));
  const tip = $("chart-tip");
  const hitR = Math.min(9, (W - L - R) / Math.max(1, y1 - y0) / 2);  // 이웃 점의 호버 영역과 겹치지 않게
  const hide = () => { tip.hidden = true; svg.querySelectorAll(".pt.active").forEach((n) => { n.classList.remove("active"); n.setAttribute("r", 2.6); }); };
  const show = (p, dot) => {
    hide();
    dot.classList.add("active"); dot.setAttribute("r", 5);
    tip.replaceChildren(el("div", p.year + "년 평균 " + p.mean + " ppm"),
      el("small", p.count + "개월 데이터" + (p.complete ? "" : " · 부분 연도")));
    tip.hidden = false;
    const box = svg.getBoundingClientRect();           // viewBox → 화면 좌표로 환산
    const left = (x(p.year) / W) * box.width;
    const half = tip.offsetWidth / 2;                  // 실제 너비로 클램프: 양 끝에서도 그래프 밖으로 안 나감
    tip.style.left = Math.min(Math.max(left, half), box.width - half) + "px";
    tip.style.top = ((y(p.mean) / H) * box.height - 12) + "px";
  };
  yearly.forEach((p) => {
    const dot = svgEl("circle", { class: "pt" + (p.complete ? "" : " partial"), cx: x(p.year), cy: y(p.mean), r: 2.6 });
    // 눈에 보이는 점은 작아서 마우스로 맞추기 어렵다: 투명한 넓은 영역(최대 반지름 9)으로 호버/터치를 받는다
    const hit = svgEl("circle", { class: "hit", cx: x(p.year), cy: y(p.mean), r: hitR });
    hit.addEventListener("mouseenter", () => show(p, dot));
    hit.addEventListener("click", () => show(p, dot));   // 터치 기기용
    hit.addEventListener("mouseleave", hide);
    svg.append(dot, hit);
  });
  svg.addEventListener("mouseleave", hide);
  $("chart-note").textContent = "속이 빈 점은 12개월이 모두 없는 부분 연도입니다. 점에 마우스를 올리면(모바일은 터치) 값이 보입니다.";
}
async function loadStatistics() {
  const s = await api("/api/data/statistics");
  drawChart(s.yearly);
}

// ---- 오늘의 AI 브리핑 ----
async function loadBriefing() {
  const text = $("briefing-text");
  text.classList.add("pending");
  try {
    const b = await api("/api/briefing");
    text.classList.remove("pending");
    text.textContent = b.text;
    const badge = $("briefing-badge");
    badge.textContent = b.ai ? "AI 생성 · " + b.model : "자동 요약 (AI 미사용)";
    badge.hidden = false;
    const ul = $("briefing-facts");
    ul.replaceChildren(...b.facts.map((f) => el("li", f)));
    $("briefing-details").hidden = false;
    $("briefing-note").textContent = "기준 관측일 " + b.asof + " · " + b.source +
      " · 새 데이터가 올라올 때 하루 1회 생성" + (b.cached ? " (저장된 브리핑)" : "");
  } catch (e) {
    text.classList.remove("pending");
    text.textContent = "브리핑을 불러오지 못했습니다. (" + e.message + ")";
  }
}

// ---- 요약 ----
async function loadSummary() {
  loadStatistics().catch(() => {});
  const s = await api("/api/data/summary");
  const body = $("summary-body");
  body.replaceChildren();
  const rows = s.count === 0 ? [["데이터", "없음"]] : [
    ["기간", s.period], ["개수", s.count + "개"],
    ["평균", s.metrics.average + " ppm"],
    ["중앙값 / 표준편차", s.metrics.median + " / " + s.metrics.stdev + " ppm"],
    ["최대", s.metrics.max + " ppm (" + s.metrics.max_date + ")"],
    ["최소", s.metrics.min + " ppm (" + s.metrics.min_date + ")"],
    ["최근 값", s.latest.value + " ppm (" + s.latest.date + ")"],
    ["트렌드", s.trend.description],
    ["연간 증가량", s.metrics.recent_annual_growth_ppm == null ? "계산 불가" : s.metrics.recent_annual_growth_ppm + " ppm/년 (최근 10개 연도 평균)"],
  ];
  rows.forEach(([k, v]) => { body.append(el("dt", k), el("dd", v)); });
}

// ---- 채팅 ----
function renderMessages(messages) {
  const box = $("messages");
  box.replaceChildren();
  if (!messages.length) box.append(el("div", "질문을 입력해 보세요.", "empty"));
  messages.forEach((m) => addBubble(m.role, m.content, m.tools || []));
}
function addBubble(role, text, tools = [], usage = null) {
  const box = $("messages");
  box.querySelector(".empty")?.remove();
  box.append(el("div", text, "msg " + role));
  if (role === "assistant" && (tools.length || usage)) {
    // 어떤 도구를 호출해 답했는지 투명하게 보여 준다 (과제: 호출 근거 설명)
    const parts = [];
    if (tools.length) parts.push("🔧 도구: " + tools.join(", "));
    if (usage) parts.push("토큰 입력 " + usage.prompt_tokens + " / 출력 " + usage.completion_tokens);
    box.append(el("div", parts.join(" · "), "toolnote"));
  }
  box.scrollTop = box.scrollHeight;
}
$("chat-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const text = $("chat-input").value.trim();
  if (!text) return;
  $("chat-input").value = "";
  addBubble("user", text);
  $("loading").hidden = false;
  $("chat-send").disabled = true;
  try {
    const r = await api("/api/chat", { method: "POST", body: JSON.stringify({ message: text, conversation_id: convId }) });
    convId = r.conversation_id;
    addBubble("assistant", r.reply, r.tools_used || [], r.usage);
  } catch (_) {
    addBubble("assistant", "(답변을 받지 못했습니다. 위 오류 메시지를 확인해 주세요.)");
  } finally {
    $("loading").hidden = true;
    $("chat-send").disabled = false;
  }
});
$("chat-new").addEventListener("click", () => { convId = null; renderMessages([]); });

// ---- 데이터 관리 (CRUD) ----
async function loadData() {
  const r = await api("/api/data?limit=" + PAGE + "&offset=" + offset + "&order=desc");
  total = r.total;
  const tbody = $("data-rows");
  tbody.replaceChildren();
  r.items.forEach((it) => {
    const tr = document.createElement("tr");
    const actions = document.createElement("td");
    const edit = el("button", "수정");
    edit.onclick = () => startEdit(it);
    const del = el("button", "삭제");
    del.onclick = () => removeData(it);
    actions.append(edit, del);
    tr.append(el("td", it.date), el("td", it.value), el("td", it.memo), actions);
    tbody.append(tr);
  });
  $("page-info").textContent = total ? (offset + 1) + "–" + Math.min(offset + PAGE, total) + " / " + total : "0";
  $("prev").disabled = offset === 0;
  $("next").disabled = offset + PAGE >= total;
}
function startEdit(it) {
  $("data-id").value = it.id; $("data-date").value = it.date;
  $("data-value").value = it.value; $("data-memo").value = it.memo;
  $("data-submit").textContent = "수정 저장"; $("data-cancel").hidden = false;
}
function resetForm() {
  $("data-form").reset(); $("data-id").value = "";
  $("data-submit").textContent = "추가"; $("data-cancel").hidden = true;
}
$("data-cancel").addEventListener("click", resetForm);
$("data-form").addEventListener("submit", async (e) => {
  e.preventDefault();
  const id = $("data-id").value;
  const body = JSON.stringify({ date: $("data-date").value, value: Number($("data-value").value), memo: $("data-memo").value });
  try {
    await api(id ? "/api/data/" + encodeURIComponent(id) : "/api/data", { method: id ? "PUT" : "POST", body });
    $("data-status").textContent = id ? "수정되었습니다." : "추가되었습니다.";
    resetForm();
    await Promise.all([loadData(), loadSummary()]);
  } catch (_) { $("data-status").textContent = ""; }
});
async function removeData(it) {
  if (!confirm(it.date + " 데이터를 삭제할까요?")) return;
  try {
    await api("/api/data/" + encodeURIComponent(it.id), { method: "DELETE" });
    $("data-status").textContent = "삭제되었습니다.";
    await Promise.all([loadData(), loadSummary()]);
  } catch (_) {}
}
// ---- 내보내기 (CSV / JSON) ----
async function exportData(format) {
  try {
    const blob = await api("/api/data/export?format=" + format, { blob: true });
    const a = document.createElement("a");
    a.href = URL.createObjectURL(blob);
    a.download = "co2_data." + format;
    document.body.append(a); a.click(); a.remove();
    URL.revokeObjectURL(a.href);
    $("data-status").textContent = format.toUpperCase() + " 파일을 내려받았습니다.";
  } catch (_) {}
}
$("refresh-monthly").addEventListener("click", async () => {
  const btn = $("refresh-monthly");
  btn.disabled = true;
  try {
    const r = await api("/api/data/refresh", { method: "POST" });
    $("data-status").textContent = r.added
      ? "새 달 " + r.added + "개를 추가했습니다: " + r.added_months.join(", ")
      : "이미 최신입니다. (원본의 최신 월: " + r.source_latest + ")";
    if (r.added) await Promise.all([loadData(), loadSummary()]);
  } catch (_) { $("data-status").textContent = ""; }
  finally { btn.disabled = false; }
});
$("export-csv").addEventListener("click", () => exportData("csv"));
$("export-json").addEventListener("click", () => exportData("json"));
$("prev").addEventListener("click", () => { offset = Math.max(0, offset - PAGE); loadData(); });
$("next").addEventListener("click", () => { offset += PAGE; loadData(); });

// ---- 대화 기록 ----
async function loadConversations() {
  const list = await api("/api/conversations");
  const ul = $("conv-list");
  ul.replaceChildren();
  if (!list.length) ul.append(el("li", "저장된 대화가 없습니다."));
  list.forEach((c) => {
    const li = document.createElement("li");
    const info = el("div", undefined, "info");
    info.append(el("div", c.title), el("small", c.message_count + "개 메시지 · " + c.updated_at.slice(0, 16).replace("T", " ")));
    const open = el("button", "불러오기");
    open.onclick = () => openConversation(c.id);
    const del = el("button", "삭제");
    del.onclick = async () => {
      if (!confirm("이 대화를 삭제할까요?")) return;
      await api("/api/conversations/" + encodeURIComponent(c.id), { method: "DELETE" });
      if (convId === c.id) { convId = null; renderMessages([]); }
      loadConversations();
    };
    li.append(info, open, del);
    ul.append(li);
  });
}
async function openConversation(id) {
  const c = await api("/api/conversations/" + encodeURIComponent(id));
  convId = c.id;
  renderMessages(c.messages);
  document.querySelector('[data-tab="chat"]').click();
}

// ---- 시작 ----
renderMessages([]);
loadSummary().catch(() => {});
loadBriefing();
