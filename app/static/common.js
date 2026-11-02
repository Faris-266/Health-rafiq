/* Rafiq shared front-end helpers. Loaded synchronously in <head> so the theme is applied before first paint. */
(function () {
  const R = (window.RAFIQ = {});
  const store = {
    get(k) { try { return localStorage.getItem(k); } catch (e) { return null; } },
    set(k, v) { try { localStorage.setItem(k, v); } catch (e) { /* private mode */ } },
  };

  /* ── theme (light / dark; defaults to the OS setting, then remembers the user's choice) ── */
  function applyTheme(t) { document.documentElement.dataset.theme = t; }
  applyTheme(store.get("rafiq-theme") || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light"));
  R.theme = () => document.documentElement.dataset.theme;
  const SUN = '<svg viewBox="0 0 24 24"><circle cx="12" cy="12" r="4"/><path d="M12 2v2M12 20v2M4.9 4.9l1.4 1.4M17.7 17.7l1.4 1.4M2 12h2M20 12h2M4.9 19.1l1.4-1.4M17.7 6.3l1.4-1.4"/></svg>';
  const MOON = '<svg viewBox="0 0 24 24"><path d="M21 12.8A9 9 0 1 1 11.2 3a7 7 0 0 0 9.8 9.8z"/></svg>';
  R.toggleTheme = function () {
    const n = R.theme() === "dark" ? "light" : "dark";
    applyTheme(n); store.set("rafiq-theme", n); paintThemeBtn();
  };
  function paintThemeBtn() {
    const b = document.getElementById("theme");
    if (!b) return;
    b.innerHTML = R.theme() === "dark" ? SUN : MOON;
    b.title = b.ariaLabel = R.t(R.theme() === "dark" ? "light" : "dark");
  }

  /* ── language ── */
  R.lang = store.get("rafiq-lang") || ((navigator.language || "").toLowerCase().startsWith("en") ? "en" : "ar");
  R.setLang = (l) => { R.lang = l; store.set("rafiq-lang", l); applyDir(); };
  function applyDir() { document.documentElement.lang = R.lang; document.documentElement.dir = R.lang === "ar" ? "rtl" : "ltr"; }
  const S = {
    ar: { light: "الوضع الفاتح", dark: "الوضع الداكن", logout: "خروج", password: "كلمة المرور", pwTitle: "تغيير كلمة المرور", pwForce: "لأمانك، اختر كلمة مرور جديدة قبل المتابعة.", pwTemp: "سجّلت الدخول بكلمة مرور مؤقتة. اكتب هذه الكلمة المؤقتة في خانة «الحالية»، ثم اختر كلمة جديدة.", pwLost: "لا تملكها؟ سجّل الخروج واطلب من المدير إعادة تعيينها.", pwSetBy: "كلمة المرور هي التي حددها المدير (لا تُعرض مرة أخرى).",
          cur: "كلمة المرور الحالية", nw: "كلمة المرور الجديدة", pwRule: "٨ أحرف على الأقل، وليست كلمة شائعة.", pwShort: "كلمة المرور الجديدة قصيرة: 8 أحرف على الأقل.", save: "حفظ", cancel: "إلغاء", copy: "نسخ", copied: "تم النسخ", close: "إغلاق",
          enrollT: "تسجيل مريض", name: "الاسم", phone: "رقم الهاتف (مع رمز الدولة)", gender: "الجنس", male: "ذكر", female: "أنثى", dialect: "اللهجة", country: "الدولة",
          conds: "الحالة", diabetes: "سكري", hypertension: "ضغط", checkin: "وقت المتابعة اليومية", doctor: "الطبيب المسؤول", meds: "الأدوية", medName: "اسم الدواء", dose: "الجرعة",
          times: "الأوقات (08:00,20:00)", mkLogin: "إنشاء حساب دخول للمريض", welcome: "إرسال رسالة الترحيب/الموافقة", enroll: "تسجيل", enrolled: "تم تسجيل المريض",
          loginMade: "حساب الدخول (يظهر مرة واحدة فقط)", breast: "فحص الثدي المبكر", birthYear: "سنة الميلاد", email: "البريد الإلكتروني (اختياري)", femaleDoc: "تفضّل طبيبة", user: "اسم المستخدم", temp: "كلمة مرور مؤقتة", none: "—", ok: "تم", error: "خطأ" },
    en: { light: "Light mode", dark: "Dark mode", logout: "Sign out", password: "Password", pwTitle: "Change password", pwForce: "For your security, choose a new password before continuing.", pwTemp: "You signed in with a temporary password. Enter that temporary password as the current password, then choose a new one.", pwLost: "Don't have it? Sign out and ask your administrator to reset it.", pwSetBy: "The password is the one the administrator chose (it is not shown again).",
          cur: "Current password", nw: "New password", pwRule: "At least 8 characters, not a common password.", pwShort: "The new password is too short: use at least 8 characters.", save: "Save", cancel: "Cancel", copy: "Copy", copied: "Copied", close: "Close",
          enrollT: "Enroll patient", name: "Name", phone: "Phone (with country code)", gender: "Gender", male: "Male", female: "Female", dialect: "Dialect", country: "Country",
          conds: "Condition", diabetes: "Diabetes", hypertension: "Hypertension", checkin: "Daily check-in time", doctor: "Responsible clinician", meds: "Medications", medName: "Medication", dose: "Dose",
          times: "Times (08:00,20:00)", mkLogin: "Create a login for the patient", welcome: "Send the welcome / consent message", enroll: "Enroll", enrolled: "Patient enrolled",
          loginMade: "Login (shown once)", breast: "Breast screening", birthYear: "Birth year", email: "Email (optional)", femaleDoc: "Prefers a female clinician", user: "Username", temp: "Temporary password", none: "—", ok: "Done", error: "Error" },
  };
  R.S = S;
  R.t = (k) => (S[R.lang] && S[R.lang][k]) || k;

  /* ── helpers ── */
  R.esc = (s) => String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
  R.nf = (n) => (n == null ? "—" : Number(n).toLocaleString(R.lang === "ar" ? "ar-EG" : "en"));
  R.toast = function (msg) {
    let t = document.getElementById("toast");
    if (!t) { t = document.createElement("div"); t.id = "toast"; t.setAttribute("role", "status"); document.body.appendChild(t); }
    t.textContent = msg; t.classList.add("show"); clearTimeout(R._tt); R._tt = setTimeout(() => t.classList.remove("show"), 2600);
  };
  R.copy = async (text) => { try { await navigator.clipboard.writeText(text); R.toast(R.t("copied")); } catch (e) { /* user can select the text */ } };

  /* ── API: cookie session; 401 → login page; forced password change handled transparently ── */
  R.api = async function api(path, opts = {}) {
    const r = await fetch(path, { credentials: "same-origin", ...opts, headers: { "Content-Type": "application/json", ...(opts.headers || {}) } });
    if (r.status === 401) { location.href = "/login"; throw new Error("Not signed in"); }
    if (r.status === 403) {
      const j = await r.clone().json().catch(() => ({}));
      if (j.detail === "password_change_required") { await R.passwordDialog(true); return api(path, opts); }
    }
    if (!r.ok) {
      let d; try { d = (await r.json()).detail; } catch (e) { d = r.statusText; }
      if (Array.isArray(d)) d = d.map((x) => x.msg || JSON.stringify(x)).join("; ");
      throw new Error(d || r.statusText);
    }
    return r.json();
  };
  R.post = (p, b) => R.api(p, { method: "POST", body: JSON.stringify(b || {}) });
  R.patch = (p, b) => R.api(p, { method: "PATCH", body: JSON.stringify(b || {}) });

  /* ── top bar wiring ── */
  R.chrome = function ({ onLang, who } = {}) {
    applyDir();
    const th = document.getElementById("theme"); if (th) { th.onclick = R.toggleTheme; paintThemeBtn(); }
    const lg = document.getElementById("lang");
    if (lg) { lg.textContent = R.lang === "ar" ? "EN" : "ع"; lg.onclick = () => { R.setLang(R.lang === "ar" ? "en" : "ar"); lg.textContent = R.lang === "ar" ? "EN" : "ع"; paintThemeBtn(); chromeText(); onLang && onLang(); }; }
    const lo = document.getElementById("logout"); if (lo && lo.tagName === "BUTTON") lo.onclick = async () => { try { await R.post("/api/auth/logout"); } catch (e) { /* ignore */ } location.href = "/login"; };
    const pw = document.getElementById("pw"); if (pw && pw.tagName === "BUTTON") pw.onclick = () => R.passwordDialog(false);
    const w = document.getElementById("who"); if (w && who) w.textContent = who;
    chromeText();
  };
  function chromeText() {
    const lo = document.getElementById("logout"); if (lo) lo.textContent = R.t("logout");
    const pw = document.getElementById("pw"); if (pw && pw.tagName === "BUTTON") pw.textContent = R.t("password");
    paintThemeBtn();
  }

  /* ── password dialog (also used when an admin forces a change at first login) ── */
  R.passwordDialog = function (force) {
    return new Promise((resolve) => {
      const d = document.createElement("dialog");
      d.innerHTML = `<form method="dialog" id="pwf"><h3>${R.t("pwTitle")}</h3>${force ? `<p class="note">${R.t("pwTemp")}</p><p class="note">${R.t("pwLost")}</p>` : ""}
        <label class="field"><span>${R.t("cur")}</span><input id="pw-c" type="password" autocomplete="current-password" required></label>
        <label class="field"><span>${R.t("nw")}</span><input id="pw-n" type="password" autocomplete="new-password" required><small class="note">${R.t("pwRule")}</small></label>
        <div class="err" id="pw-e"></div>
        <div class="dlg-actions">${force ? `<button type="button" class="btn" id="pw-out">${R.t("logout")}</button>` : `<button type="button" class="btn" id="pw-x">${R.t("cancel")}</button>`}<button class="btn primary" id="pw-ok">${R.t("save")}</button></div></form>`;
      document.body.appendChild(d);
      if (force) d.addEventListener("cancel", (e) => e.preventDefault());
      const out = d.querySelector("#pw-out"); if (out) out.onclick = async () => { try { await R.post("/api/auth/logout"); } catch (e) { /* ignore */ } location.href = "/login"; };
      const x = d.querySelector("#pw-x"); if (x) x.onclick = () => { d.close(); d.remove(); resolve(false); };
      d.querySelector("#pwf").onsubmit = async (e) => {
        e.preventDefault();
        if (d.querySelector("#pw-n").value.length < 8) { d.querySelector("#pw-e").textContent = R.t("pwShort"); return; }
        try {
          await R.api("/api/auth/change-password", { method: "POST", body: JSON.stringify({ current: d.querySelector("#pw-c").value, new: d.querySelector("#pw-n").value }) });
          d.close(); d.remove(); R.toast(R.t("ok")); resolve(true);
        } catch (err) { d.querySelector("#pw-e").textContent = err.message; }
      };
      d.showModal();
    });
  };

  /* ── secret display (temporary passwords: shown once) ── */
  R.showLogin = function (login, title) {
    const d = document.createElement("dialog");
    d.innerHTML = `<h3>${R.esc(title || R.t("loginMade"))}</h3><p class="note">${R.t("user")}</p><div class="secret">${R.esc(login.username)}</div>
      ${login.temp_password ? `<p class="note" style="margin-top:10px">${R.t("temp")}</p><div class="secret">${R.esc(login.temp_password)}</div>` : `<p class="note" style="margin-top:10px">${R.t("pwSetBy")}</p>`}
      <div class="dlg-actions"><button class="btn" id="cp">${R.t("copy")}</button><button class="btn primary" id="cl">${R.t("close")}</button></div>`;
    document.body.appendChild(d);
    d.querySelector("#cp").onclick = () => R.copy(login.temp_password ? `${login.username} / ${login.temp_password}` : login.username);
    d.querySelector("#cl").onclick = () => { d.close(); d.remove(); };
    d.showModal();
  };

  /* ── enroll-patient dialog (admin console + clinician dashboard) ── */
  R.enrollDialog = function ({ clinicians = [], dialects = {}, countries = [], isAdmin = false, programme = "chronic", onDone }) {
    const showBreast = programme !== "chronic", showChronic = programme !== "breast";
    const d = document.createElement("dialog");
    const opt = (o, sel) => Object.entries(o).map(([k, v]) => `<option value="${R.esc(k)}" ${k === sel ? "selected" : ""}>${R.esc(v)}</option>`).join("");
    const medRow = () => `<div class="row2" data-med><label class="field"><span>${R.t("medName")}</span><input class="m-n" dir="auto"></label><label class="field"><span>${R.t("dose")}</span><input class="m-d" dir="auto"></label>
      <label class="field" style="grid-column:1/-1"><span>${R.t("times")}</span><input class="m-t" value="08:00" dir="ltr"></label></div>`;
    d.innerHTML = `<form id="ef"><h3>${R.t("enrollT")}</h3>
      <label class="field"><span>${R.t("name")}</span><input id="e-n" required dir="auto" maxlength="80"></label>
      <div class="row2"><label class="field"><span>${R.t("phone")}</span><input id="e-p" required dir="ltr" placeholder="962790000000" inputmode="tel"></label>
      <label class="field"><span>${R.t("birthYear")}</span><input id="e-by" type="number" min="1900" max="2010" dir="ltr" placeholder="1980"></label></div>
      <label class="field"><span>${R.t("email")}</span><input id="e-em" type="email" dir="ltr"></label>
      <div class="row2"><label class="field"><span>${R.t("gender")}</span><select id="e-g"><option value="f">${R.t("female")}</option><option value="m">${R.t("male")}</option></select></label>
      <label class="field"><span>${R.t("dialect")}</span><select id="e-d">${opt(dialects, R.lang === "en" ? "en" : "levantine")}</select></label></div>
      <div class="row2"><label class="field"><span>${R.t("country")}</span><select id="e-c">${countries.map((c) => `<option>${c}</option>`).join("")}</select></label>
      <label class="field"><span>${R.t("checkin")}</span><input id="e-t" type="time" value="08:00"></label></div>
      <div class="checks"><b class="note">${R.t("conds")}</b>${showBreast ? `<label><input type="checkbox" id="e-br" ${programme === "breast" ? "checked" : ""}> ${R.t("breast")}</label>` : ""}${showChronic ? `<label><input type="checkbox" id="e-dm" checked> ${R.t("diabetes")}</label><label><input type="checkbox" id="e-ht"> ${R.t("hypertension")}</label>` : ""}</div>
      ${isAdmin ? `<label class="field"><span>${R.t("doctor")}</span><select id="e-cl"><option value="">${R.t("none")}</option>${clinicians.map((c) => `<option value="${c.id}">${R.esc(c.name)}</option>`).join("")}</select></label>` : ""}
      <div id="e-meds" class="hidden"><b class="note">${R.t("meds")}</b>${medRow()}${medRow()}</div>
      <div class="checks">${showBreast ? `<label><input type="checkbox" id="e-fd"> ${R.t("femaleDoc")}</label>` : ""}<label><input type="checkbox" id="e-lg" checked> ${R.t("mkLogin")}</label><label><input type="checkbox" id="e-w" checked> ${R.t("welcome")}</label></div>
      <div class="err" id="e-e"></div>
      <div class="dlg-actions"><button type="button" class="btn" id="e-x">${R.t("cancel")}</button><button class="btn primary">${R.t("enroll")}</button></div></form>`;
    document.body.appendChild(d);
    const on = (id) => { const el = d.querySelector(id); return !!(el && el.checked); };
    const syncMeds = () => d.querySelector("#e-meds").classList.toggle("hidden", !(on("#e-dm") || on("#e-ht")));
    ["#e-dm", "#e-ht"].forEach((id) => { const el = d.querySelector(id); if (el) el.onchange = syncMeds; });
    syncMeds();
    d.querySelector("#e-x").onclick = () => { d.close(); d.remove(); };
    d.querySelector("#ef").onsubmit = async (e) => {
      e.preventDefault();
      const conditions = [on("#e-br") && "breast", on("#e-dm") && "diabetes", on("#e-ht") && "hypertension"].filter(Boolean);
      const medications = [...d.querySelectorAll("[data-med]")].map((r) => ({ name: r.querySelector(".m-n").value.trim(), dose: r.querySelector(".m-d").value.trim() || null,
        times: r.querySelector(".m-t").value.split(",").map((x) => x.trim()).filter(Boolean) })).filter((m) => m.name);
      const cl = d.querySelector("#e-cl"), by = d.querySelector("#e-by").value;
      try {
        const out = await R.post("/api/patients", { name: d.querySelector("#e-n").value.trim(), phone: d.querySelector("#e-p").value.replace(/[\s+\-()]/g, ""), gender: d.querySelector("#e-g").value,
          dialect: d.querySelector("#e-d").value, country: d.querySelector("#e-c").value, conditions, checkin_time: d.querySelector("#e-t").value || "08:00",
          birth_year: by ? +by : null, email: d.querySelector("#e-em").value.trim() || null, prefers_female_clinician: on("#e-fd"),
          clinician_id: cl && cl.value ? +cl.value : null, medications, create_login: d.querySelector("#e-lg").checked, send_welcome: d.querySelector("#e-w").checked });
        d.close(); d.remove(); R.toast(R.t("enrolled"));
        if (out.login) R.showLogin(out.login);
        onDone && onDone(out);
      } catch (err) { d.querySelector("#e-e").textContent = err.message; }
    };
    d.showModal();
  };

  /* ── line chart (SVG) shared by dashboard and patient portal ── */
  R.lineChart = function (series, { band, yMin, yMax, W = 420, H = 170, targetLabel = "target", noData = "—" }) {
    const P = { l: 34, r: 8, t: 8, b: 20 }, all = series.flatMap((s) => s.pts);
    if (!all.length) return `<div class="note">${noData}</div>`;
    const t0 = Math.min(...all.map((p) => p.t)), t1 = Math.max(...all.map((p) => p.t)) || t0 + 1;
    const X = (x) => P.l + (t1 === t0 ? 0.5 : (x - t0) / (t1 - t0)) * (W - P.l - P.r), Y = (y) => P.t + (1 - (y - yMin) / (yMax - yMin)) * (H - P.t - P.b);
    let g = "";
    if (band) g += `<rect x="${P.l}" y="${Y(band[1])}" width="${W - P.l - P.r}" height="${Y(band[0]) - Y(band[1])}" fill="var(--green-soft)"><title>${targetLabel} ${band[0]}–${band[1]}</title></rect>`;
    for (let i = 0; i <= 3; i++) { const v = yMin + (yMax - yMin) * i / 3, y = Y(v); g += `<line x1="${P.l}" x2="${W - P.r}" y1="${y}" y2="${y}" stroke="var(--line)"/><text x="${P.l - 5}" y="${y + 4}" text-anchor="end" font-size="10" fill="var(--muted)">${Math.round(v)}</text>`; }
    const fmt = (d) => new Date(d).toLocaleDateString(R.lang === "ar" ? "ar-EG" : "en", { month: "short", day: "numeric" });
    g += `<text x="${P.l}" y="${H - 5}" font-size="10" fill="var(--muted)">${fmt(t0)}</text><text x="${W - P.r}" y="${H - 5}" font-size="10" text-anchor="end" fill="var(--muted)">${fmt(t1)}</text>`;
    const col = (l) => (l === 2 ? "var(--red)" : l === 1 ? "var(--amber)" : "var(--green)");
    series.forEach((s) => {
      g += `<polyline fill="none" stroke="${s.color}" stroke-width="1.6" stroke-dasharray="${s.dash || ""}" points="${s.pts.map((p) => X(p.t) + "," + Y(p.v)).join(" ")}"/>`;
      s.pts.forEach((p) => (g += `<circle cx="${X(p.t)}" cy="${Y(p.v)}" r="3.6" fill="${s.dash ? "var(--surface)" : col(p.l)}" stroke="${s.dash ? s.color : "var(--surface)"}" stroke-width="1.2"><title>${p.v} · ${fmt(p.t)}</title></circle>`));
    });
    return `<svg class="chart" viewBox="0 0 ${W} ${H}" role="img">${g}</svg>`;
  };

  R.ago = function (iso) {
    if (!iso) return "";
    const s = (Date.now() - new Date(iso + "Z")) / 1000, ar = R.lang === "ar";
    const u = s < 60 ? (ar ? "الآن" : "now") : s < 3600 ? R.nf(Math.round(s / 60)) + (ar ? "د" : "m") : s < 86400 ? R.nf(Math.round(s / 3600)) + (ar ? "س" : "h") : R.nf(Math.round(s / 86400)) + (ar ? "ي" : "d");
    return s < 60 ? u : ar ? "قبل " + u : u + " ago";
  };
  R.store = store;
  applyDir();
})();
