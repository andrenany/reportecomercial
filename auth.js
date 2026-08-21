/* Acceso simple (cliente). No es seguridad fuerte en un sitio público. */
const ADL_AUTH_KEY = "adl_reporte_auth_v1";

/** hash SHA-256 de "adl|<user>|<pass>" */
const ADL_USERS = {
  ariofrio: "f536036e9008ddfe2eb2458071847dec309d3fde2c09e3763362edfef1f29731",
  gleiva: "f439cabbbb7f9810b170436b96ceacd56fcb21fb2c231703c918f282da460ed5",
  admin: "9a8b7448d1d6460e5785fd2de0550d1b1e320a763d5196a106b688929a12af03",
  pve: "9b6e87a73b9ccd9b31fa282fe9340ac3d5a76ea1b112c8d962b07ddfcd9c66ab",
};

/** Roles: full = todo el dashboard; calendario = solo calendario veterinarios */
const ADL_ROLES = {
  ariofrio: "full",
  gleiva: "full",
  admin: "full",
  pve: "calendario",
};

const ADL_HOME = {
  full: "dashboard_facturacion.html",
  calendario: "consulta_facturacion.html",
};

async function adlHash(user, pass) {
  const raw = "adl|" + String(user).trim().toLowerCase() + "|" + String(pass);
  const data = new TextEncoder().encode(raw);
  const buf = await crypto.subtle.digest("SHA-256", data);
  return [...new Uint8Array(buf)].map((b) => b.toString(16).padStart(2, "0")).join("");
}

function adlSession() {
  try {
    return JSON.parse(sessionStorage.getItem(ADL_AUTH_KEY) || "null");
  } catch {
    return null;
  }
}

function adlRole() {
  const s = adlSession();
  if (!s || !s.user) return null;
  return s.role || ADL_ROLES[s.user] || "full";
}

function adlHomeFor(role) {
  return ADL_HOME[role] || ADL_HOME.full;
}

function adlSetSession(user, role) {
  sessionStorage.setItem(
    ADL_AUTH_KEY,
    JSON.stringify({
      user,
      role: role || ADL_ROLES[user] || "full",
      at: Date.now(),
    })
  );
}

function adlClearSession() {
  sessionStorage.removeItem(ADL_AUTH_KEY);
}

function adlRequireLogin() {
  const path = (location.pathname.split("/").pop() || "").toLowerCase();
  if (path === "login.html" || path === "") return;

  const sess = adlSession();
  if (!sess) {
    const next = encodeURIComponent(path || "dashboard_facturacion.html");
    location.replace("login.html?next=" + next);
    return;
  }

  const role = sess.role || ADL_ROLES[sess.user] || "full";
  // Usuario PVE: solo puede estar en consulta facturación (calendario)
  if (role === "calendario" && path !== "consulta_facturacion.html") {
    location.replace("consulta_facturacion.html");
  }
}

async function adlTryLogin(user, pass) {
  const u = String(user || "").trim().toLowerCase();
  const expected = ADL_USERS[u];
  if (!expected) return false;
  const got = await adlHash(u, pass);
  if (got !== expected) return false;
  adlSetSession(u, ADL_ROLES[u] || "full");
  return true;
}

function adlLogout() {
  adlClearSession();
  location.href = "login.html";
}

/** Restringe UI de consulta_facturacion al calendario + reglas (rol calendario). */
function adlApplyCalendarioOnly() {
  if (adlRole() !== "calendario") return;

  const allowed = new Set(["calendario", "reglas-cal"]);
  document.querySelectorAll(".tabs button").forEach((b) => {
    const t = b.dataset.tab;
    if (!allowed.has(t)) {
      b.style.display = "none";
      b.classList.remove("active");
    } else {
      b.style.display = "";
    }
  });
  // Por defecto abre calendario
  document.querySelectorAll(".tabs button").forEach((b) => {
    b.classList.toggle("active", b.dataset.tab === "calendario");
  });
  document.querySelectorAll(".tab-pane").forEach((p) => {
    p.classList.toggle("active", p.id === "tab-calendario");
  });

  document.querySelectorAll(".nav-links a").forEach((a) => {
    const href = (a.getAttribute("href") || "").toLowerCase();
    if (href !== "consulta_facturacion.html") a.style.display = "none";
    else a.classList.add("active");
  });

  const sub = document.querySelector(".subhead h2");
  if (sub) sub.textContent = "Calendario veterinarios";
  const subp = document.querySelector(".subhead p");
  if (subp) subp.textContent = "Acceso PVE · calendario y reglas (solo lectura)";
}

adlRequireLogin();
