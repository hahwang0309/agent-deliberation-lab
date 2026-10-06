// API 호출 공통 래퍼 (같은 출처, 인증은 브라우저가 처리)
const API = "/api/v1";

async function api(path, { method = "GET", body } = {}) {
  const res = await fetch(API + path, {
    method,
    credentials: "same-origin",
    headers: body !== undefined ? { "Content-Type": "application/json" } : {},
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = data && data.error ? data.error : data && data.detail && data.detail.error ? data.detail.error : null;
    throw new Error(err ? `${err.message}${err.field ? ` (${err.field})` : ""}` : `HTTP ${res.status}`);
  }
  return data;
}

const STATUS_LABELS = {
  draft: "대기",
  running: "진행 중",
  awaiting_human: "발언 대기",
  reporting: "보고서 작성 중",
  completed: "완료",
  stopped: "중지됨",
  failed: "실패",
  interrupted: "중단됨",
};

function statusBadge(status) {
  const span = document.createElement("span");
  span.className = `badge ${status}`;
  span.textContent = STATUS_LABELS[status] || status;
  return span;
}

function el(tag, attrs = {}, ...children) {
  const node = document.createElement(tag);
  for (const [k, v] of Object.entries(attrs)) {
    if (k === "class") node.className = v;
    else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
    else node.setAttribute(k, v);
  }
  for (const child of children) {
    if (child == null) continue;
    node.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
  return node;
}

function formatDate(iso) {
  if (!iso) return "";
  return new Date(iso).toLocaleString("ko-KR", { dateStyle: "short", timeStyle: "short" });
}
