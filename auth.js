/* Acceso simple (cliente). No es seguridad fuerte en un sitio público. */
const ADL_AUTH_KEY = "adl_reporte_auth_v1";
const ADL_USERS = {
  ariofrio: "f536036e9008ddfe2eb2458071847dec309d3fde2c09e3763362edfef1f29731",
  gleiva: "f439cabbbb7f9810b170436b96ceacd56fcb21fb2c231703c918f282da460ed5",
  admin: "9a8b7448d1d6460e5785fd2de0550d1b1e320a763d5196a106b688929a12af03",
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

function adlSetSession(user) {
  sessionStorage.setItem(
    ADL_AUTH_KEY,
    JSON.stringify({ user, at: Date.now() })
  );
}

function adlClearSession() {
  sessionStorage.removeItem(ADL_AUTH_KEY);
}

function adlRequireLogin() {
  const path = (location.pathname.split("/").pop() || "").toLowerCase();
  if (path === "login.html" || path === "") return;
  if (!adlSession()) {
    const next = encodeURIComponent(path || "dashboard_facturacion.html");
    location.replace("login.html?next=" + next);
  }
}

async function adlTryLogin(user, pass) {
  const u = String(user || "").trim().toLowerCase();
  const expected = ADL_USERS[u];
  if (!expected) return false;
  const got = await adlHash(u, pass);
  if (got !== expected) return false;
  adlSetSession(u);
  return true;
}

function adlLogout() {
  adlClearSession();
  location.href = "login.html";
}

adlRequireLogin();
