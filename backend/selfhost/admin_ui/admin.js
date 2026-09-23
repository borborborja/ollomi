"use strict";

let accessToken = "";
let currentUser = null;
let profiles = [];
let config = [];
const $ = (id) => document.getElementById(id);
const labels = {stt: "Transcripció", chat: "Processament i xat", embedding: "Embeddings"};
const defaults = {
  openai: "https://api.openai.com/v1", openrouter: "https://openrouter.ai/api/v1",
  "ollama-cloud": "https://ollama.com/v1", gemini: "https://generativelanguage.googleapis.com",
  assemblyai: "https://api.assemblyai.com/v2", deepgram: "https://api.deepgram.com/v1",
  voyage: "https://api.voyageai.com/v1", cohere: "https://api.cohere.com/v2"
};
const allowed = {
  stt: ["custom", "openai", "whisper", "gemini", "assemblyai", "deepgram"],
  chat: ["custom", "openai", "openrouter", "ollama", "ollama-cloud"],
  embedding: ["custom", "openai", "ollama", "voyage", "cohere"]
};

function node(tag, text, className) {
  const item = document.createElement(tag);
  if (text !== undefined) item.textContent = text;
  if (className) item.className = className;
  return item;
}
function clear(element) { element.replaceChildren(); }
function notice(message, error = false) {
  $("notice").textContent = message;
  $("notice").classList.toggle("error", error);
}
async function api(path, options = {}) {
  const response = await fetch(path, {
    ...options,
    headers: {"Content-Type": "application/json", Authorization: `Bearer ${accessToken}`, ...(options.headers || {})},
    cache: "no-store"
  });
  if (response.status === 401) {
    logout();
    throw new Error("La sessió ha caducat. Torna a entrar.");
  }
  const body = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(typeof body.detail === "string" ? body.detail : `Error ${response.status}`);
  return body;
}
async function task(operation, success) {
  try { await operation(); if (success) notice(success); }
  catch (error) { notice(error.message, true); }
}
function logout() {
  accessToken = "";
  currentUser = null;
  $("shell").hidden = true;
  $("login").hidden = false;
  $("login-form").reset();
}
function page(name) {
  document.querySelectorAll(".page").forEach((section) => { section.hidden = section.id !== name; });
  document.querySelectorAll(".nav").forEach((button) => button.classList.toggle("active", button.dataset.page === name));
  notice("");
}
async function loadOverview() {
  const [server, status, users] = await Promise.all([
    api("/v1/server-info"), api("/v1/ai-status"), api("/v1/admin/users")
  ]);
  const target = $("overview-content"); clear(target);
  const summary = [
    ["Servidor", `${server.name} · ${server.version}`, `${server.local_only ? "Només xarxa local" : "Proveïdors externs permesos"}`],
    ["Usuaris", String(users.length), `${users.filter((user) => user.enabled).length} actius`],
    ["MCP", server.capabilities.includes("mcp") ? "Actiu" : "Desactivat", server.mcp_url || ""],
    ...Object.entries(labels).map(([purpose, label]) => [label, `${status[purpose].profiles.length} models`, status[purpose].managed_by_env ? "Gestionats per .env" : "Gestionats al servidor"])
  ];
  for (const [title, value, detail] of summary) {
    const card = node("article", undefined, "card");
    card.append(node("h2", title), node("strong", value), node("p", detail)); target.append(card);
  }
}
function action(label, handler, secondary = true) {
  const button = node("button", label, secondary ? "secondary" : "");
  button.type = "button"; button.addEventListener("click", handler); return button;
}
function badge(value, locked = false) { return node("span", value, `badge${locked ? " lock" : ""}`); }
function modelFormReset() {
  $("model-form").reset();
  $("model-form").elements.profile_id.value = "";
  $("model-form-title").textContent = "Afegeix un model";
  updateProviders();
}
function updateProviders() {
  const form = $("model-form");
  const purpose = form.elements.purpose.value;
  const provider = form.elements.provider;
  [...provider.options].forEach((option) => { option.disabled = !allowed[purpose].includes(option.value); });
  if (!allowed[purpose].includes(provider.value)) provider.value = "custom";
  if (defaults[provider.value] && !form.elements.base_url.value) form.elements.base_url.value = defaults[provider.value];
}
function editProfile(profile) {
  const form = $("model-form");
  for (const key of ["name", "purpose", "provider", "model", "base_url"]) form.elements[key].value = profile[key] || "";
  form.elements.profile_id.value = profile.id;
  form.elements.external.checked = profile.external;
  form.elements.enabled.checked = profile.enabled;
  form.elements.api_key.value = "";
  updateProviders();
  $("model-form-title").textContent = "Edita el model";
  form.scrollIntoView({behavior: "smooth"});
}
async function moveProfile(purpose, index, direction) {
  const rows = profiles.filter((profile) => profile.purpose === purpose && profile.enabled && profile.managed_by !== "env")
    .sort((a, b) => (a.priority ?? 999999) - (b.priority ?? 999999));
  const other = index + direction;
  if (other < 0 || other >= rows.length) return;
  [rows[index], rows[other]] = [rows[other], rows[index]];
  await api("/v1/admin/ai-profile-order", {method: "PUT", body: JSON.stringify({purpose, ids: rows.map((row) => row.id)})});
  await loadModels(); notice("Ordre desat");
}
async function loadModels() {
  [profiles, config] = await Promise.all([api("/v1/admin/ai-profiles"), api("/v1/admin/config")]);
  const selection = config.find((item) => item.key === "allow_user_model_selection");
  $("model-selection").checked = selection.value === true;
  $("model-selection").disabled = !selection.editable;
  $("selection-lock").textContent = selection.editable ? "" : "Fixat a .env";
  const target = $("model-groups"); clear(target);
  for (const purpose of ["stt", "chat", "embedding"]) {
    target.append(node("h2", labels[purpose]));
    const panel = node("div", undefined, "panel");
    const rows = profiles.filter((profile) => profile.purpose === purpose)
      .sort((a, b) => (a.priority ?? 999999) - (b.priority ?? 999999));
    const locked = rows.some((profile) => profile.managed_by === "env" && profile.enabled);
    if (!rows.length) panel.append(node("p", "Encara no hi ha cap model configurat."));
    rows.forEach((profile, index) => {
      const row = node("div", undefined, "row"); const main = node("div", undefined, "row-main");
      const title = node("strong", `${profile.name} · ${profile.model}`);
      title.append(badge(profile.managed_by === "env" ? ".env" : `Prioritat ${index + 1}`, profile.managed_by === "env"));
      if (!profile.enabled) title.append(badge("Inactiu", true));
      main.append(title, node("small", `${profile.provider} · ${profile.status} · ${profile.base_url || ""}`));
      const actions = node("div", undefined, "row-actions");
      actions.append(action("Prova", () => task(async () => {
        await api(`/v1/admin/ai-profiles/${profile.id}/validate`, {method: "POST"});
        await loadModels();
      }, "Connexió correcta")));
      if (!locked && profile.managed_by !== "env") {
        actions.append(action("Edita", () => editProfile(profile)));
        if (profile.enabled) {
          const position = rows.filter((item) => item.enabled).findIndex((item) => item.id === profile.id);
          const up = action("↑", () => task(() => moveProfile(purpose, position, -1))); up.setAttribute("aria-label", `Puja ${profile.name}`);
          const down = action("↓", () => task(() => moveProfile(purpose, position, 1))); down.setAttribute("aria-label", `Baixa ${profile.name}`);
          actions.append(up, down);
        }
      }
      row.append(main, actions); panel.append(row);
    });
    if (locked) panel.prepend(node("p", "Aquests models i l’ordre de fallback es defineixen a .env i són de només lectura.", "hint"));
    target.append(panel);
  }
  const form = $("model-form");
  const selectedPurpose = form.elements.purpose.value;
  form.querySelector("button[type=submit]").disabled = profiles.some((profile) => profile.purpose === selectedPurpose && profile.enabled && profile.managed_by === "env");
}
async function loadUsers() {
  const users = await api("/v1/admin/users"); const target = $("user-list"); clear(target);
  for (const user of users) {
    const row = node("div", undefined, "row"); const main = node("div", undefined, "row-main");
    main.append(node("strong", `${user.display_name || user.email} · ${user.email}`),
      node("small", `${user.admin ? "Administrador" : "Usuari"} · ${user.enabled ? "Actiu" : "Desactivat"}`));
    const actions = node("div", undefined, "row-actions");
    if (user.id !== currentUser.id) actions.append(action(user.enabled ? "Desactiva" : "Activa", () => task(async () => {
      await api(`/v1/admin/users/${user.id}`, {method: "PATCH", body: JSON.stringify({enabled: !user.enabled})}); await loadUsers();
    }, "Usuari actualitzat")));
    const password = node("input"); password.type = "password"; password.minLength = 12;
    password.placeholder = "Nova contrasenya"; password.setAttribute("aria-label", `Nova contrasenya per a ${user.email}`);
    actions.append(password, action("Canvia", () => task(async () => {
      if (password.value.length < 12) throw new Error("La contrasenya ha de tenir 12 caràcters com a mínim.");
      await api(`/v1/admin/users/${user.id}`, {method: "PATCH", body: JSON.stringify({password: password.value})});
      password.value = "";
      if (user.id === currentUser.id) { logout(); throw new Error("Contrasenya canviada. Torna a entrar."); }
    }, "Contrasenya canviada")));
    row.append(main, actions); target.append(row);
  }
}
async function loadConfig() {
  config = await api("/v1/admin/config"); const target = $("config-list"); clear(target);
  const groups = [
    ["Aplicació i accés", (item) => !item.key.startsWith("OLLOMI_") && !["database_url","redis_url","data_dir","secret_key","typesense_url","typesense_key"].includes(item.key) && !item.key.includes("url") && !item.key.startsWith("mcp_") && !item.key.startsWith("voiceprint_")],
    ["Serveis i integracions", (item) => !item.key.startsWith("OLLOMI_") && (item.key.includes("url") || item.key.startsWith("mcp_") || item.key.startsWith("voiceprint_"))],
    ["Infraestructura Docker", (item) => item.key.startsWith("OLLOMI_") || ["database_url","redis_url","data_dir","secret_key","typesense_url","typesense_key","POSTGRES_PASSWORD","TYPESENSE_API_KEY","COMPOSE_FILE","WHISPER_MODEL","DIARIZATION"].includes(item.key)]
  ];
  for (const [title, filter] of groups) {
    target.append(node("h2", title)); const panel = node("div", undefined, "panel");
    for (const item of config.filter(filter)) {
      const row = node("div", undefined, "config-row"); const label = node("label", item.env);
      label.append(node("small", item.source === "environment" ? "Fixat a .env" : item.source === "panel" ? "Valor del panell" : item.source === "default" ? "Valor predeterminat" : "No configurat"));
      const input = node("input"); input.id = `setting-${item.key}`;
      input.type = item.type === "secret" ? "password" : item.type === "number" ? "number" : item.type === "boolean" ? "checkbox" : "text";
      if (item.type === "boolean") input.checked = item.value === true;
      else if (item.type !== "secret") input.value = item.value ?? "";
      else input.placeholder = item.has_value ? "Configurat (ocult)" : "Sense valor";
      input.disabled = !item.editable;
      label.htmlFor = input.id;
      const actions = node("div", undefined, "row-actions");
      if (item.editable) {
        actions.append(action("Desa", () => task(async () => {
          const value = item.type === "boolean" ? input.checked : item.type === "number" ? Number(input.value) : input.value;
          if (item.type === "secret" && !value) throw new Error("Escriu un valor abans de desar.");
          const result = await api(`/v1/admin/config/${item.key}`, {method: "PUT", body: JSON.stringify({value})});
          await loadConfig();
          if (result.restart_required) notice("Desat. Reinicia els serveis Ollomi perquè s’apliqui completament.");
          else notice("Configuració desada");
        })));
        if (item.source === "panel") actions.append(action("Restableix", () => task(async () => {
          await api(`/v1/admin/config/${item.key}`, {method: "DELETE"}); await loadConfig();
        }, "Valor predeterminat restaurat")));
      } else actions.append(badge("Bloquejat", true));
      row.append(label, input, actions); panel.append(row);
    }
    target.append(panel);
  }
}

$("login-form").addEventListener("submit", async (event) => {
  event.preventDefault(); $("login-error").textContent = "";
  const form = event.currentTarget;
  try {
    const response = await fetch("/v1/auth/login", {method: "POST", headers: {"Content-Type": "application/json"},
      body: JSON.stringify({email: form.elements.email.value, password: form.elements.password.value}), cache: "no-store"});
    if (!response.ok) throw new Error("Correu o contrasenya incorrectes.");
    const data = await response.json();
    if (!data.user.admin) throw new Error("Cal un compte administrador.");
    accessToken = data.access_token; currentUser = data.user;
    $("signed-in").textContent = data.user.email;
    $("login").hidden = true; $("shell").hidden = false; form.elements.password.value = "";
    page("overview"); await loadOverview();
  } catch (error) { accessToken = ""; $("login-error").textContent = error.message; }
});
document.querySelectorAll(".nav").forEach((button) => button.addEventListener("click", () => task(async () => {
  page(button.dataset.page);
  await ({overview: loadOverview, models: loadModels, users: loadUsers, config: loadConfig})[button.dataset.page]();
})));
$("logout").addEventListener("click", logout);
$("model-form").elements.purpose.addEventListener("change", () => { updateProviders(); loadModels().catch((error) => notice(error.message, true)); });
$("model-form").elements.provider.addEventListener("change", () => {
  const form = $("model-form"); if (defaults[form.elements.provider.value]) form.elements.base_url.value = defaults[form.elements.provider.value];
  form.elements.external.checked = !!defaults[form.elements.provider.value];
});
$("model-cancel").addEventListener("click", modelFormReset);
$("model-selection").addEventListener("change", (event) => task(async () => {
  await api("/v1/admin/config/allow_user_model_selection", {method: "PUT", body: JSON.stringify({value: event.target.checked})});
  await loadModels();
}, "Permís actualitzat"));
$("model-form").addEventListener("submit", (event) => task(async () => {
  event.preventDefault(); const form = event.currentTarget;
  const id = form.elements.profile_id.value;
  const body = Object.fromEntries(["name", "purpose", "provider", "model", "base_url"].map((key) => [key, form.elements[key].value]));
  body.external = form.elements.external.checked; body.enabled = form.elements.enabled.checked;
  if (form.elements.api_key.value) body.api_key = form.elements.api_key.value;
  await api(id ? `/v1/admin/ai-profiles/${id}` : "/v1/admin/ai-profiles", {method: id ? "PUT" : "POST", body: JSON.stringify(body)});
  modelFormReset(); await loadModels();
}, "Model desat"));
$("user-form").addEventListener("submit", (event) => task(async () => {
  event.preventDefault(); const form = event.currentTarget;
  const body = Object.fromEntries(["name", "email", "password"].map((key) => [key, form.elements[key].value]));
  body.admin = form.elements.admin.checked;
  await api("/v1/admin/users", {method: "POST", body: JSON.stringify(body)});
  form.reset(); await loadUsers();
}, "Usuari creat"));
