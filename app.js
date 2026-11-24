// Persuadir Sinais — lógica do app
// Fonte de dados: Worker (Cloudflare) que expõe o KV de sinais, protegido por login

const API_URL = "https://persuadir-sinais-api.sa-mesakcruz.workers.dev";
const REFRESH_MS = 30000; // 30s é suficiente; o backend só grava a cada 1 min
const TOKEN_KEY = "persuadir-sinais-token";
const ROLE_KEY = "persuadir-sinais-role";

const SYMBOLS = [
  { key: "BTC_USD", label: "BTC", sub: "Bitcoin / USD", kraken: "btc-usd" },
  { key: "ETH_USD", label: "ETH", sub: "Ethereum / USD", kraken: "eth-usd" },
  { key: "SOL_USD", label: "SOL", sub: "Solana / USD", kraken: "sol-usd" },
  { key: "LINK_USD", label: "LINK", sub: "Chainlink / USD", kraken: "link-usd" },
];

const ICONS = {
  sun: '<circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
  moon: '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
  eye: '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"></path><circle cx="12" cy="12" r="3"></circle>',
  eyeOff: '<path d="M17.94 17.94A10.94 10.94 0 0 1 12 20c-7 0-11-8-11-8a18.4 18.4 0 0 1 5.06-5.94M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19m-6.72-1.07a3 3 0 1 1-4.24-4.24"></path><line x1="1" y1="1" x2="23" y2="23"></line>',
};

const els = {
  authView: document.getElementById("auth-view"),
  authBrand: document.getElementById("auth-brand"),
  authCard: document.getElementById("auth-card"),
  authNotice: document.getElementById("auth-notice"),
  authNoticeText: document.getElementById("auth-notice-text"),
  dashboardView: document.getElementById("dashboard-view"),
  settingsView: document.getElementById("settings-view"),
  adminView: document.getElementById("admin-view"),
  cardsContainer: document.getElementById("cards-container"),
  updatedLabel: document.getElementById("updated-label"),
  liveDot: document.getElementById("live-dot"),
  loginForm: document.getElementById("login-form"),
  loginUsername: document.getElementById("login-username"),
  loginPassword: document.getElementById("login-password"),
  loginError: document.getElementById("login-error"),
  loginSubmit: document.getElementById("login-submit"),
  adminRow: document.getElementById("admin-row"),
  usersList: document.getElementById("users-list"),
  createUserForm: document.getElementById("create-user-form"),
  pushToggleBtn: document.getElementById("push-toggle-btn"),
};

// ---------- Sessão ----------
function getToken() { try { return localStorage.getItem(TOKEN_KEY); } catch (e) { return null; } }
function setToken(token) { try { localStorage.setItem(TOKEN_KEY, token); } catch (e) {} }
function clearToken() { try { localStorage.removeItem(TOKEN_KEY); } catch (e) {} }
function getRole() { try { return localStorage.getItem(ROLE_KEY) || "user"; } catch (e) { return "user"; } }
function setRole(role) { try { localStorage.setItem(ROLE_KEY, role || "user"); } catch (e) {} }

// ---------- Tema ----------
function getStoredTheme() { try { return localStorage.getItem("persuadir-sinais-theme"); } catch (e) { return null; } }
function storeTheme(theme) { try { localStorage.setItem("persuadir-sinais-theme", theme); } catch (e) {} }
function applyTheme(theme) {
  document.body.setAttribute("data-theme", theme);
  const icon = theme === "dark" ? ICONS.sun : ICONS.moon;
  ["theme-icon-auth", "theme-icon-dash"].forEach((id) => {
    const svg = document.getElementById(id);
    if (svg) { svg.innerHTML = icon; svg.setAttribute("stroke", "currentColor"); }
  });
}
function toggleTheme() {
  const current = document.body.getAttribute("data-theme");
  const next = current === "dark" ? "light" : "dark";
  applyTheme(next);
  storeTheme(next);
}
(function initTheme() {
  const prefersLight = window.matchMedia && window.matchMedia("(prefers-color-scheme: light)").matches;
  const theme = getStoredTheme() || (prefersLight ? "light" : "dark");
  applyTheme(theme);
})();
document.getElementById("theme-toggle-auth").addEventListener("click", (e) => { e.stopPropagation(); toggleTheme(); });
document.getElementById("theme-toggle-dash").addEventListener("click", toggleTheme);

// ---------- Navegação entre telas ----------
function showView(view) {
  [els.authView, els.dashboardView, els.settingsView, els.adminView].forEach((v) => v.classList.remove("active"));
  view.classList.add("active");
}

function enterDashboard() {
  cardsSettled = false;
  els.cardsContainer.classList.remove("settled");
  els.adminRow.hidden = getRole() !== "admin";
  showView(els.dashboardView);
  loadData();
  refreshPushButton();
  if (!pollTimer) pollTimer = setInterval(loadData, REFRESH_MS);
}

function goToLogin(message) {
  stopPolling();
  clearToken();
  els.loginForm.reset();
  if (message) {
    els.loginError.textContent = message;
    els.loginError.hidden = false;
  } else {
    els.loginError.hidden = true;
  }
  els.authBrand.classList.add("docked");
  els.authCard.classList.add("visible");
  showView(els.authView);
}

document.getElementById("open-settings").addEventListener("click", () => showView(els.settingsView));
document.getElementById("close-settings").addEventListener("click", () => showView(els.dashboardView));
document.getElementById("open-admin").addEventListener("click", () => { showView(els.adminView); loadUsers(); });
document.getElementById("close-admin").addEventListener("click", () => showView(els.settingsView));

document.getElementById("logout-btn").addEventListener("click", async () => {
  const token = getToken();
  if (token) {
    try {
      await fetch(API_URL + "/logout", { method: "POST", headers: { Authorization: "Bearer " + token } });
    } catch (e) { /* mesmo se falhar, encerramos a sessão localmente */ }
  }
  goToLogin();
});

// ---------- Senha visível/oculta ----------
document.getElementById("toggle-password").addEventListener("click", () => {
  const btn = document.getElementById("toggle-password");
  const isHidden = els.loginPassword.type === "password";
  els.loginPassword.type = isHidden ? "text" : "password";
  btn.querySelector("svg").innerHTML = isHidden ? ICONS.eyeOff : ICONS.eye;
});
document.getElementById("toggle-password").querySelector("svg").innerHTML = ICONS.eye;

// ---------- Criar conta / Esqueci a senha ----------
function showAuthNotice(text) {
  els.authNoticeText.textContent = text;
  els.authNotice.classList.add("visible");
}
document.getElementById("link-create").addEventListener("click", (e) => {
  e.preventDefault();
  showAuthNotice("O acesso ao Persuadir Sinais é por convite. Fale com o administrador do sistema para receber suas credenciais.");
});
document.getElementById("link-forgot").addEventListener("click", (e) => {
  e.preventDefault();
  showAuthNotice("Para redefinir sua senha, entre em contato com o administrador do sistema.");
});
document.getElementById("notice-back").addEventListener("click", () => {
  els.authNotice.classList.remove("visible");
});

// ---------- Login ----------
els.loginForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = els.loginUsername.value.trim();
  const password = els.loginPassword.value;
  if (!username || !password) return;

  els.loginSubmit.disabled = true;
  els.loginSubmit.innerHTML = '<span class="btn-spinner"></span> Entrando...';
  els.loginError.hidden = true;

  try {
    const res = await fetch(API_URL + "/login", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Não foi possível entrar.");
    setToken(data.token);
    setRole(data.role || "user");
    enterDashboard();
  } catch (err) {
    els.loginError.textContent = err.message || "Não foi possível entrar. Tente novamente.";
    els.loginError.hidden = false;
    const card = els.authCard;
    card.classList.remove("shake");
    void card.offsetWidth;
    card.classList.add("shake");
  } finally {
    els.loginSubmit.disabled = false;
    els.loginSubmit.textContent = "Entrar";
  }
});

// ---------- Dados ----------
let pollTimer = null;
let cardsSettled = false;

function stopPolling() { if (pollTimer) { clearInterval(pollTimer); pollTimer = null; } }

function formatScore(v) {
  if (typeof v !== "number") return "—";
  const sign = v > 0 ? "+" : "";
  return sign + v.toFixed(2);
}

function timeAgo(tsSeconds) {
  if (!tsSeconds) return "";
  const diffMs = Date.now() - tsSeconds * 1000;
  const mins = Math.floor(diffMs / 60000);
  if (mins < 1) return "agora mesmo";
  if (mins === 1) return "há 1 min";
  if (mins < 60) return `há ${mins} min`;
  const hours = Math.floor(mins / 60);
  if (hours === 1) return "há 1h";
  return `há ${hours}h`;
}

function buildSparkline(history) {
  const points = Array.isArray(history) ? history.slice(-40) : [];
  if (points.length < 2) return '<svg viewBox="0 0 100 40"></svg>';
  const min = Math.min(...points);
  const max = Math.max(...points);
  const range = max - min || 1;
  const stepX = 100 / (points.length - 1);
  const coords = points.map((v, i) => {
    const x = i * stepX;
    const y = 36 - ((v - min) / range) * 32;
    return `${x.toFixed(2)},${y.toFixed(2)}`;
  });
  const last = points[points.length - 1];
  const lineColor = last >= 0 ? "var(--buy)" : "var(--sell)";
  const lastX = (points.length - 1) * stepX;
  const lastY = 36 - ((last - min) / range) * 32;
  return `
    <svg viewBox="0 0 100 40" preserveAspectRatio="none">
      <polyline class="spark-line" pathLength="1" points="${coords.join(" ")}" fill="none" stroke="${lineColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>
      <circle class="spark-dot" cx="${lastX.toFixed(2)}" cy="${lastY.toFixed(2)}" r="2.4" fill="${lineColor}"/>
    </svg>`;
}

function buildSignalBadge(signal) {
  if (!signal) return "";
  const isBuy = signal.action === "COMPRA";
  const cls = isBuy ? "buy" : "sell";
  const label = isBuy ? "COMPRA" : "VENDA";
  const price = typeof signal.price_at_signal === "number" ? signal.price_at_signal.toLocaleString("pt-BR", { maximumFractionDigits: 2 }) : "—";
  return `
    <div class="signal-badge ${cls}">
      <span class="signal-tag" style="color:var(--${cls})"><span>${label}</span></span>
      <span class="signal-meta">em $${price} · ${timeAgo(signal.emitted_at)}</span>
    </div>`;
}

function buildKrakenLink(def) {
  return `
    <a class="kraken-link" href="https://pro.kraken.com/app/trade/${def.kraken}" target="_blank" rel="noopener">
      <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><path d="M18 13v6a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2V8a2 2 0 0 1 2-2h6"></path><polyline points="15 3 21 3 21 9"></polyline><line x1="10" y1="14" x2="21" y2="3"></line></svg>
      Abrir na Kraken
    </a>`;
}

function buildCard(def, data, index) {
  const history = data ? data.score_history : [];
  const lastScore = Array.isArray(history) && history.length ? history[history.length - 1] : null;
  const scoreClass = lastScore == null ? "" : lastScore >= 0 ? "pos" : "neg";
  const accuracy = data && data.accuracy ? data.accuracy : { acertos: 0, total: 0 };
  const pct = accuracy.total > 0 ? Math.round((accuracy.acertos / accuracy.total) * 100) : null;
  const pendingList = (data && Array.isArray(data.pending_signals)) ? data.pending_signals : [];
  const activeSignal = pendingList.length ? pendingList[pendingList.length - 1] : null;
  const delay = (index || 0) * 0.09;

  return `
    <div class="card" style="--d: ${delay}s">
      <div class="card-top">
        <div class="symbol-block">
          <div class="symbol-badge">${def.label}</div>
          <div>
            <div class="symbol-name">${def.label}</div>
            <div class="symbol-sub">${def.sub}</div>
          </div>
        </div>
        <div class="score-value ${scoreClass}">${formatScore(lastScore)}</div>
      </div>
      <div class="sparkline-wrap">${buildSparkline(history)}</div>
      <div class="card-footer">
        <span>Precisão histórica</span>
        <span class="accuracy-value">${pct == null ? "sem dados ainda" : `${pct}% (${accuracy.acertos}/${accuracy.total})`}</span>
      </div>
      ${buildSignalBadge(activeSignal)}
      ${buildKrakenLink(def)}
    </div>`;
}

async function loadData() {
  const token = getToken();
  if (!token) { goToLogin(); return; }

  try {
    const res = await fetch(API_URL + "/signals", { cache: "no-store", headers: { Authorization: "Bearer " + token } });
    if (res.status === 401) { goToLogin("Sessão expirada. Entre novamente."); return; }
    if (!res.ok) throw new Error("HTTP " + res.status);

    const data = await res.json();
    els.cardsContainer.innerHTML = SYMBOLS.map((def, i) => buildCard(def, data[def.key], i)).join("");
    els.updatedLabel.textContent = "Atualizado " + new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    els.liveDot.style.background = "var(--buy)";

    if (!cardsSettled) {
      cardsSettled = true;
      setTimeout(() => els.cardsContainer.classList.add("settled"), 1700);
    }
  } catch (err) {
    els.cardsContainer.innerHTML = `<div class="error-state">Não foi possível carregar os sinais agora. Tentando novamente...</div>`;
    els.updatedLabel.textContent = "Falha na atualização";
    els.liveDot.style.background = "var(--sell)";
    console.error("Persuadir Sinais — erro ao buscar dados:", err);
  }
}

// ---------- Administração ----------
async function loadUsers() {
  const token = getToken();
  els.usersList.innerHTML = '<div class="settings-row"><span class="label">Carregando...</span></div>';
  try {
    const res = await fetch(API_URL + "/admin/list-users", { headers: { Authorization: "Bearer " + token } });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Falha ao carregar.");
    els.usersList.innerHTML = data.users.map((u) => `
      <div class="user-row">
        <span class="u-name">${u.username}</span>
        <span class="u-role ${u.role === "admin" ? "admin" : ""}">${u.role === "admin" ? "admin" : "usuário"}</span>
      </div>`).join("") || '<div class="settings-row"><span class="label">Nenhum usuário ainda</span></div>';
  } catch (err) {
    els.usersList.innerHTML = `<div class="settings-row"><span class="label">${err.message}</span></div>`;
  }
}

async function sha256Hex(text) {
  const data = new TextEncoder().encode(text);
  const digest = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(digest)].map((b) => b.toString(16).padStart(2, "0")).join("");
}
function randomSaltHex(bytes = 16) {
  const arr = new Uint8Array(bytes);
  crypto.getRandomValues(arr);
  return [...arr].map((b) => b.toString(16).padStart(2, "0")).join("");
}

els.createUserForm.addEventListener("submit", async (e) => {
  e.preventDefault();
  const username = document.getElementById("new-username").value.trim().toLowerCase();
  const password = document.getElementById("new-password").value;
  const role = document.getElementById("new-role").value;
  const errEl = document.getElementById("admin-error");
  const okEl = document.getElementById("admin-success");
  const submitBtn = document.getElementById("create-user-submit");
  errEl.hidden = true; okEl.hidden = true;
  if (!username || !password) return;

  submitBtn.disabled = true;
  submitBtn.innerHTML = '<span class="btn-spinner"></span> Criando...';
  try {
    const salt = randomSaltHex();
    const hash = await sha256Hex(salt + password);
    const res = await fetch(API_URL + "/admin/create-user", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + getToken() },
      body: JSON.stringify({ username, role, salt, hash }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.error || "Não foi possível criar o acesso.");
    okEl.textContent = `Acesso criado para "${username}".`;
    okEl.hidden = false;
    els.createUserForm.reset();
    loadUsers();
  } catch (err) {
    errEl.textContent = err.message;
    errEl.hidden = false;
  } finally {
    submitBtn.disabled = false;
    submitBtn.textContent = "Criar acesso";
  }
});

// ---------- Notificações push ----------
function urlBase64ToUint8Array(base64String) {
  const padding = "=".repeat((4 - (base64String.length % 4)) % 4);
  const base64 = (base64String + padding).replace(/-/g, "+").replace(/_/g, "/");
  const raw = atob(base64);
  return Uint8Array.from([...raw].map((c) => c.charCodeAt(0)));
}

async function refreshPushButton() {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) {
    els.pushToggleBtn.textContent = "Indisponível";
    els.pushToggleBtn.disabled = true;
    return;
  }
  try {
    const reg = await navigator.serviceWorker.ready;
    const sub = await reg.pushManager.getSubscription();
    if (sub) {
      els.pushToggleBtn.textContent = "Ativado";
      els.pushToggleBtn.classList.add("on");
    } else {
      els.pushToggleBtn.textContent = "Ativar";
      els.pushToggleBtn.classList.remove("on");
    }
  } catch (e) { /* silencioso */ }
}

els.pushToggleBtn.addEventListener("click", async () => {
  if (!("serviceWorker" in navigator) || !("PushManager" in window)) return;
  const reg = await navigator.serviceWorker.ready;
  const existing = await reg.pushManager.getSubscription();

  if (existing) {
    await existing.unsubscribe();
    await refreshPushButton();
    return;
  }

  els.pushToggleBtn.disabled = true;
  try {
    const permission = await Notification.requestPermission();
    if (permission !== "granted") { els.pushToggleBtn.disabled = false; return; }

    const keyRes = await fetch(API_URL + "/vapid-public-key");
    const { publicKey } = await keyRes.json();
    const sub = await reg.pushManager.subscribe({
      userVisibleOnly: true,
      applicationServerKey: urlBase64ToUint8Array(publicKey),
    });
    await fetch(API_URL + "/subscribe", {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + getToken() },
      body: JSON.stringify(sub),
    });
  } catch (e) {
    console.error("Persuadir Sinais — erro ao ativar notificações:", e);
  } finally {
    els.pushToggleBtn.disabled = false;
    refreshPushButton();
  }
});

// ---------- Animação de entrada: "a linha que chega" ----------
function animateIcon() {
  const path = document.getElementById("icon-line");
  const dot = document.getElementById("icon-dot");
  const ring = document.getElementById("icon-dot-ring");
  const nameBlock = document.getElementById("app-name");
  if (!path || !dot || !ring) return;

  const length = path.getTotalLength();
  path.style.strokeDasharray = length;
  path.style.strokeDashoffset = length;
  dot.style.opacity = "0";
  dot.style.transform = "scale(0)";
  ring.style.opacity = "0";

  path.getBoundingClientRect();
  path.style.transition = "stroke-dashoffset 1.1s cubic-bezier(0.65,0,0.35,1)";
  requestAnimationFrame(() => { path.style.strokeDashoffset = "0"; });

  setTimeout(() => {
    dot.style.transition = "opacity 0.3s ease, transform 0.45s cubic-bezier(0.34,1.56,0.64,1)";
    dot.style.opacity = "1";
    dot.style.transform = "scale(1)";
    ring.style.opacity = "1";
    ring.classList.add("ring-pulse");
  }, 1050);

  if (nameBlock) {
    nameBlock.style.transform = "translateY(6px)";
    setTimeout(() => {
      nameBlock.style.transition = "opacity 0.5s ease, transform 0.5s ease";
      nameBlock.style.opacity = "1";
      nameBlock.style.transform = "translateY(0)";
    }, 1300);
  }
}

// ---------- Fluxo de inicialização ----------
// A marca entra centralizada e sozinha; em seguida "doca" no topo enquanto o
// cartão de login sobe por baixo dela — uma única jornada, sem corte abrupto.
function initEntryFlow() {
  animateIcon();
  const hasSession = !!getToken();

  if (hasSession) {
    setTimeout(enterDashboard, 1900);
    return;
  }

  setTimeout(() => {
    els.authBrand.classList.add("docked");
    els.authCard.classList.add("visible");
  }, 2100);
}
document.addEventListener("DOMContentLoaded", initEntryFlow);

// ---------- Service worker ----------
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("service-worker.js").catch(() => {});
  });
}
