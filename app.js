// Persuadir Sinais — lógica do app
// Fonte de dados: Worker público (Cloudflare) que expõe o KV de sinais

const API_URL = "https://persuadir-sinais-api.sa-mesakcruz.workers.dev";
const REFRESH_MS = 30000; // 30s é suficiente; o backend só grava a cada 1 min

const SYMBOLS = [
  { key: "BTC_USD", label: "BTC", sub: "Bitcoin / USD" },
  { key: "SOL_USD", label: "SOL", sub: "Solana / USD" },
  { key: "LINK_USD", label: "LINK", sub: "Chainlink / USD" },
];

const ICONS = {
  sun: '<circle cx="12" cy="12" r="4"></circle><path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M6.34 17.66l-1.41 1.41M19.07 4.93l-1.41 1.41"/>',
  moon: '<path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79z"/>',
};

const els = {
  entryView: document.getElementById("entry-view"),
  dashboardView: document.getElementById("dashboard-view"),
  settingsView: document.getElementById("settings-view"),
  cardsContainer: document.getElementById("cards-container"),
  updatedLabel: document.getElementById("updated-label"),
  liveDot: document.getElementById("live-dot"),
};

// ---------- Tema ----------
function getStoredTheme() {
  try { return localStorage.getItem("persuadir-sinais-theme"); } catch (e) { return null; }
}
function storeTheme(theme) {
  try { localStorage.setItem("persuadir-sinais-theme", theme); } catch (e) {}
}
function applyTheme(theme) {
  document.body.setAttribute("data-theme", theme);
  const icon = theme === "dark" ? ICONS.sun : ICONS.moon;
  ["theme-icon-entry", "theme-icon-dash"].forEach((id) => {
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
document.getElementById("theme-toggle-entry").addEventListener("click", (e) => { e.stopPropagation(); toggleTheme(); });
document.getElementById("theme-toggle-dash").addEventListener("click", toggleTheme);

// ---------- Navegação entre telas ----------
function showView(view) {
  [els.entryView, els.dashboardView, els.settingsView].forEach((v) => v.classList.remove("active"));
  view.classList.add("active");
}
els.entryView.addEventListener("click", () => {
  showView(els.dashboardView);
  loadData();
  if (!pollTimer) pollTimer = setInterval(loadData, REFRESH_MS);
});
document.getElementById("open-settings").addEventListener("click", () => showView(els.settingsView));
document.getElementById("close-settings").addEventListener("click", () => showView(els.dashboardView));

// ---------- Dados ----------
let pollTimer = null;

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
  if (points.length < 2) {
    return '<svg viewBox="0 0 100 40"></svg>';
  }
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
      <polyline points="${coords.join(" ")}" fill="none" stroke="${lineColor}" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" vector-effect="non-scaling-stroke"/>
      <circle cx="${lastX.toFixed(2)}" cy="${lastY.toFixed(2)}" r="2.4" fill="${lineColor}"/>
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

function buildCard(def, data) {
  const history = data ? data.score_history : [];
  const lastScore = Array.isArray(history) && history.length ? history[history.length - 1] : null;
  const scoreClass = lastScore == null ? "" : lastScore >= 0 ? "pos" : "neg";
  const accuracy = data && data.accuracy ? data.accuracy : { acertos: 0, total: 0 };
  const pct = accuracy.total > 0 ? Math.round((accuracy.acertos / accuracy.total) * 100) : null;
  const pendingList = (data && Array.isArray(data.pending_signals)) ? data.pending_signals : [];
  const activeSignal = pendingList.length ? pendingList[pendingList.length - 1] : null;

  return `
    <div class="card">
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
    </div>`;
}

async function loadData() {
  try {
    const res = await fetch(API_URL, { cache: "no-store" });
    if (!res.ok) throw new Error("HTTP " + res.status);
    const data = await res.json();
    els.cardsContainer.innerHTML = SYMBOLS.map((def) => buildCard(def, data[def.key])).join("");
    els.updatedLabel.textContent = "Atualizado " + new Date().toLocaleTimeString("pt-BR", { hour: "2-digit", minute: "2-digit" });
    els.liveDot.style.background = "var(--buy)";
  } catch (err) {
    els.cardsContainer.innerHTML = `<div class="error-state">Não foi possível carregar os sinais agora. Tentando novamente...</div>`;
    els.updatedLabel.textContent = "Falha na atualização";
    els.liveDot.style.background = "var(--sell)";
    console.error("Persuadir Sinais — erro ao buscar dados:", err);
  }
}

// ---------- Animação de entrada: "a linha que chega" ----------
function animateIcon() {
  const path = document.getElementById("icon-line");
  const dot = document.getElementById("icon-dot");
  const ring = document.getElementById("icon-dot-ring");
  const nameBlock = document.querySelector(".app-name");
  if (!path || !dot || !ring) return;

  const length = path.getTotalLength();
  path.style.strokeDasharray = length;
  path.style.strokeDashoffset = length;
  dot.style.opacity = "0";
  dot.style.transform = "scale(0)";
  ring.style.opacity = "0";

  // força reflow antes de iniciar a transição
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
document.addEventListener("DOMContentLoaded", animateIcon);

// ---------- Service worker ----------
if ("serviceWorker" in navigator) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("service-worker.js").catch(() => {});
  });
}
