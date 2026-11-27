// Shared helpers for LiveLink Vet pages.
const LL = (() => {
  const API = "/api/v1";
  const TOKEN_KEY = "livelink_token";
  const mem = {};

  // Storage can be blocked (private mode, strict settings): fall back to memory.
  const store = {
    get(k, session) { try { return (session ? sessionStorage : localStorage).getItem(k); } catch { return mem[k] ?? null; } },
    set(k, v, session) { try { (session ? sessionStorage : localStorage).setItem(k, v); } catch { mem[k] = v; } },
    del(k, session) { try { (session ? sessionStorage : localStorage).removeItem(k); } catch { delete mem[k]; } },
    json(k, fallback) { try { return JSON.parse(store.get(k) ?? "null") ?? fallback; } catch { return fallback; } },
  };

  // Field data is user-supplied: never insert it as raw HTML.
  const esc = (v) => String(v ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  const fmt = (n) => (typeof n === "number" ? n.toLocaleString() : esc(n));
  const ago = (iso) => {
    const mins = Math.round((Date.now() - new Date(iso)) / 60000);
    if (mins < 1) return "just now";
    if (mins < 60) return `${mins} min ago`;
    if (mins < 1440) return `${Math.round(mins / 60)} h ago`;
    return `${Math.round(mins / 1440)} d ago`;
  };

  // ---------- theme ----------
  function applyTheme(t) {
    if (t === "light" || t === "dark") document.documentElement.dataset.theme = t;
    else delete document.documentElement.dataset.theme;
  }
  function isDark() {
    const t = document.documentElement.dataset.theme;
    return t ? t === "dark" : matchMedia("(prefers-color-scheme: dark)").matches;
  }
  function initThemeToggle(btn, onChange) {
    applyTheme(store.get("livelink_theme"));
    const paint = () => {
      btn.innerHTML = isDark()
        ? '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>'
        : '<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
      btn.setAttribute("aria-label", isDark() ? "Switch to light theme" : "Switch to dark theme");
    };
    btn.addEventListener("click", () => {
      const next = isDark() ? "light" : "dark";
      applyTheme(next); store.set("livelink_theme", next); paint(); onChange && onChange();
    });
    matchMedia("(prefers-color-scheme: dark)").addEventListener?.("change", () => { paint(); onChange && onChange(); });
    paint();
  }

  // ---------- auth + api ----------
  const token = () => store.get(TOKEN_KEY, true) || store.get(TOKEN_KEY);
  function setToken(t, remember) {
    store.del(TOKEN_KEY, true); store.del(TOKEN_KEY);
    if (t) store.set(TOKEN_KEY, t, !remember);
  }
  async function api(path, opts = {}) {
    const headers = { ...(opts.body ? { "Content-Type": "application/json" } : {}), ...(token() ? { Authorization: "Bearer " + token() } : {}) };
    const res = await fetch(API + path, { ...opts, headers: { ...headers, ...(opts.headers || {}) } });
    if (!res.ok) {
      const err = new Error(res.status === 403 ? "forbidden" : res.status === 401 ? "unauthorized" : `HTTP ${res.status}`);
      err.status = res.status;
      try { err.detail = (await res.json()).detail; } catch { /* no body */ }
      throw err;
    }
    return res.status === 204 ? null : res.json();
  }
  async function login(phone, password, remember) {
    const res = await fetch(API + "/auth/login", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ phone_number: phone, password }),
    });
    if (res.status === 429) throw new Error("Too many attempts. Please wait 15 minutes and try again.");
    if (!res.ok) throw new Error("Phone number or password is incorrect.");
    setToken((await res.json()).access_token, remember);
  }

  return { API, store, esc, fmt, ago, initThemeToggle, isDark, token, setToken, api, login };
})();
