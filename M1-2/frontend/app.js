const API = (window.API_BASE_URL || "").replace(/\/$/, "");
const PAGE = 20;
const $ = (id) => document.getElementById(id);
let convId = null;   // 현재 대화 (null = 새 대화)
let offset = 0;
let total = 0;

// ---- API 호출 (콜드스타트 안내 + 오류 표시) ----
async function api(path, options = {}) {
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

// ---- 요약 ----
async function loadSummary() {
  const s = await api("/api/data/summary");
  const body = $("summary-body");
  body.replaceChildren();
  const rows = s.count === 0 ? [["데이터", "없음"]] : [
    ["기간", s.period], ["개수", s.count + "개"],
    ["평균", s.metrics.average + " ppm"],
    ["최대", s.metrics.max + " ppm (" + s.metrics.max_date + ")"],
    ["최소", s.metrics.min + " ppm (" + s.metrics.min_date + ")"],
    ["최근 값", s.latest.value + " ppm (" + s.latest.date + ")"],
    ["트렌드", s.trend.description],
  ];
  rows.forEach(([k, v]) => { body.append(el("dt", k), el("dd", v)); });
}

// ---- 채팅 ----
function renderMessages(messages) {
  const box = $("messages");
  box.replaceChildren();
  if (!messages.length) box.append(el("div", "질문을 입력해 보세요.", "empty"));
  messages.forEach((m) => addBubble(m.role, m.content));
}
function addBubble(role, text) {
  const box = $("messages");
  box.querySelector(".empty")?.remove();
  box.append(el("div", text, "msg " + role));
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
    addBubble("assistant", r.reply);
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
