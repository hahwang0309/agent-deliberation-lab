// API 호출 공통 래퍼 (같은 출처, 쿠키 인증 + CSRF 헤더, 401 시 토큰 갱신 1회 재시도)
const API = "/api/v1";

function csrfToken() {
  const row = document.cookie.split("; ").find(c => c.startsWith("csrf_token="));
  return row ? decodeURIComponent(row.slice("csrf_token=".length)) : "";
}

function goLogin() {
  const next = encodeURIComponent(location.pathname + location.search);
  location.href = `/login.html?next=${next}`;
}

async function api(path, { method = "GET", body, retry = true } = {}) {
  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (method !== "GET") headers["X-CSRF-Token"] = csrfToken();
  const res = await fetch(API + path, {
    method, credentials: "same-origin", headers,
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });

  if (res.status === 401 && retry && !path.startsWith("/auth/")) {
    const refreshed = await fetch(API + "/auth/refresh", { method: "POST", credentials: "same-origin" });
    if (refreshed.ok) return api(path, { method, body, retry: false });
    goLogin();
    throw new Error("로그인이 필요합니다.");
  }
  if (res.status === 204) return null;
  const data = await res.json().catch(() => null);
  if (!res.ok) {
    const err = data && data.detail && data.detail.error ? data.detail.error : data && data.error ? data.error : null;
    if (err && err.code === "PASSWORD_CHANGE_REQUIRED") location.href = "/change-password.html";
    const e = new Error(err ? `${err.message}${err.field ? ` (${err.field})` : ""}` : `HTTP ${res.status}`);
    e.code = err && err.code;
    e.status = res.status;
    throw e;
  }
  return data;
}

// 로그인 필요 페이지: 현재 사용자 조회 + 상단 메뉴 표시
async function requireLogin({ admin = false } = {}) {
  let me;
  try {
    me = await api("/auth/me");
  } catch (e) {
    goLogin();
    throw e;
  }
  if (me.must_change_password) {
    location.href = "/change-password.html";
    throw new Error("비밀번호 변경 필요");
  }
  if (admin && me.role !== "admin") {
    location.href = "/";
    throw new Error("관리자 전용");
  }
  renderNav(me);
  return me;
}

function renderNav(me) {
  const header = document.querySelector("header.top");
  if (!header || header.querySelector(".nav")) return;
  const logout = el("button", { onclick: async () => {
    await api("/auth/logout", { method: "POST" }).catch(() => {});
    location.href = "/login.html";
  } }, "로그아웃");
  header.append(el("div", { class: "nav" },
    el("a", { href: "/" }, "토론"),
    me.role === "admin" ? el("a", { href: "/admin.html" }, "관리자") : null,
    el("span", { class: "muted" }, `${me.name} (${me.email})`),
    logout));
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
