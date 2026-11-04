"use strict";
/* Frontend: cliente publico OAuth 2.0 (authorization code + PKCE). Sin dependencias salvo Leaflet. */

const $ = (s) => document.querySelector(s);
const REDIRECT_URI = `${location.origin}/`;
const st = { cfg: null, token: null, claims: null, veredas: [], mapa: null, capaVeredas: null, capaRuta: null, base: null };

// ---------------------------------------------------------------- utilidades
function esc(s) {
  return String(s ?? "").replace(/[&<>"']/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
}
function b64url(bytes) {
  return btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
}
function aleatorio(n = 32) { return b64url(crypto.getRandomValues(new Uint8Array(n))); }
function decodificarJwt(t) {
  const p = t.split(".")[1].replace(/-/g, "+").replace(/_/g, "/");
  return JSON.parse(decodeURIComponent(escape(atob(p))));
}
function svg(id, cls = "ic") { return `<svg class="${cls}" aria-hidden="true"><use href="#i-${id}"/></svg>`; }
// tipo: false (neutro), true/"error", "ok" (exito)
function estado(msg, tipo = false, el = "#estado") {
  const e = $(el), err = tipo === true || tipo === "error", ok = tipo === "ok";
  e.classList.toggle("error", err); e.classList.toggle("exito", ok);
  e.innerHTML = msg ? `${err ? svg("error") : ok ? svg("ok") : ""}<span>${esc(msg)}</span>` : "";
}
function ocupado(on) {
  const b = $("#btn-generar");
  b.setAttribute("aria-busy", String(on)); $("#centro").setAttribute("aria-busy", String(on));
  if (on) b.disabled = true;
}
function fmtMin(m) { const h = Math.floor(m / 60), r = Math.round(m % 60); return h ? `${h} h ${r} min` : `${r} min`; }

async function api(ruta, opciones = {}) {
  const r = await fetch(ruta, {
    ...opciones,
    headers: { "Content-Type": "application/json", Authorization: `Bearer ${st.token}`, ...(opciones.headers || {}) },
  });
  if (r.status === 401) { cerrarSesion(); throw new Error("Sesión expirada, ingrese de nuevo."); }
  const datos = await r.json().catch(() => ({}));
  if (!r.ok) {
    const d = datos.detail;
    throw new Error(Array.isArray(d) ? d.map((x) => x.msg).join("; ") : d || `Error ${r.status}`);
  }
  return datos;
}

// ---------------------------------------------------------------- OAuth 2.0 + PKCE
async function iniciarLogin() {
  const verifier = aleatorio(48);
  const challenge = b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
  const state = aleatorio(16);
  sessionStorage.setItem("pkce", JSON.stringify({ verifier, state }));
  const q = new URLSearchParams({
    response_type: "code", client_id: st.cfg.client_id, redirect_uri: REDIRECT_URI,
    code_challenge: challenge, code_challenge_method: "S256", state,
  });
  location.assign(`${st.cfg.auth_url}/oauth/authorize?${q}`);
}

async function procesarCallback() {
  const q = new URLSearchParams(location.search);
  if (!q.has("code")) return;
  history.replaceState(null, "", "/"); // retira el codigo de la URL
  const guardado = JSON.parse(sessionStorage.getItem("pkce") || "{}");
  sessionStorage.removeItem("pkce");
  if (!guardado.state || guardado.state !== q.get("state")) throw new Error("Parámetro state inválido (posible CSRF).");
  const r = await fetch(`${st.cfg.auth_url}/oauth/token`, {
    method: "POST",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code", code: q.get("code"), redirect_uri: REDIRECT_URI,
      client_id: st.cfg.client_id, code_verifier: guardado.verifier,
    }),
  });
  const t = await r.json();
  if (!r.ok) throw new Error(t.error_description || "No se pudo obtener el token");
  guardarToken(t.access_token);
}

function guardarToken(tok) {
  st.token = tok; st.claims = decodificarJwt(tok);
  try { sessionStorage.setItem("tok", tok); } catch (_) { /* almacenamiento no disponible */ }
}

function cerrarSesion() {
  st.token = null; st.claims = null;
  try { sessionStorage.removeItem("tok"); } catch (_) {}
  mostrarVista();
}

function tieneScope(s) { return (st.claims?.scope || "").split(" ").includes(s); }

// ---------------------------------------------------------------- vistas
function mostrarVista() {
  const logueado = !!st.token && st.claims && st.claims.exp * 1000 > Date.now();
  $("#vista-login").hidden = logueado;
  $("#vista-app").hidden = !logueado;
  $("#sesion").hidden = !logueado;
  if (!logueado) return;
  const nombre = st.claims.name || st.claims.sub;
  $("#usuario-nombre").textContent = nombre;
  $("#usuario-ini").textContent = nombre.split(/[\s._-]+/).filter(Boolean).slice(0, 2).map((x) => x[0].toUpperCase()).join("");
  $("#usuario-rol").textContent = (st.claims.roles || []).join(", ");
  $("#tab-plan").hidden = !tieneScope("rutas:generar");
  $("#tab-aud").hidden = !tieneScope("auditoria:leer");
  seleccionarTab(tieneScope("rutas:generar") ? "plan" : "aud");
}

function seleccionarTab(cual) {
  for (const t of ["plan", "aud"]) {
    $(`#tab-${t}`).setAttribute("aria-selected", String(t === cual));
    $(`#tab-${t}`).tabIndex = t === cual ? 0 : -1;
    $(`#panel-${t}`).hidden = t !== cual;
  }
  if (cual === "plan") { iniciarMapa(); if ($("#sel-municipio").options.length <= 1) cargarMunicipios(); }
  if (cual === "aud") cargarAuditoria();
}

// ---------------------------------------------------------------- planificacion
function iniciarMapa() {
  if (st.mapa) { setTimeout(() => st.mapa.invalidateSize(), 50); return; }
  st.mapa = L.map("mapa").setView([4.6, -74.1], 8);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    maxZoom: 18, attribution: "&copy; OpenStreetMap · Veredas: DANE/Esri Colombia",
    referrerPolicy: "strict-origin-when-cross-origin", // OSM bloquea (403) peticiones sin Referer
  }).addTo(st.mapa);
  st.capaVeredas = L.layerGroup().addTo(st.mapa);
  st.capaRuta = L.layerGroup().addTo(st.mapa);
}

async function cargarMunicipios() {
  try {
    estado("Cargando municipios de Cundinamarca…");
    const ms = await api("/api/municipios");
    const sel = $("#sel-municipio");
    sel.innerHTML = `<option value="">Seleccione un municipio (${ms.length})</option>` +
      ms.map((m) => `<option value="${esc(m.codigo)}">${esc(m.nombre)}</option>`).join("");
    estado("");
  } catch (e) { estado(e.message, true); }
}

async function cargarVeredas(cod) {
  st.capaVeredas.clearLayers(); st.capaRuta.clearLayers();
  $("#resultado").hidden = true; st.veredas = [];
  $("#leyenda").hidden = true; $("#mapa-vacio").hidden = !!cod;
  $("#lista-veredas").innerHTML = `<p class="lista-vacia">${cod ? "Cargando veredas…" : "Seleccione primero un municipio."}</p>`;
  if (!cod) { estado(""); return actualizarConteo(); }
  try {
    estado("Consultando veredas en la fuente de datos abiertos…");
    const d = await api(`/api/municipios/${encodeURIComponent(cod)}/veredas`);
    st.veredas = d.veredas; st.base = d.base;
    const sug = new Set(d.sugeridas);
    $("#lista-veredas").innerHTML = d.veredas.map((v) => `
      <label data-nombre="${esc(v.nombre.toLowerCase())}">
        <input type="checkbox" value="${esc(v.codigo)}" ${sug.has(v.codigo) ? "checked" : ""}>
        <span>${esc(v.nombre)}</span>
      </label>`).join("");
    const grupo = [];
    for (const v of d.veredas) {
      const pol = L.polygon(v.poligono, { color: "#1a7350", weight: sug.has(v.codigo) ? 1.5 : 1, fillOpacity: sug.has(v.codigo) ? 0.22 : 0.04 })
        .bindTooltip(v.nombre);
      pol.addTo(st.capaVeredas); grupo.push(pol);
    }
    L.marker([d.base.lat, d.base.lon], { icon: icono(null, true), title: d.base.nombre })
      .bindPopup(`<strong>${esc(d.base.nombre)}</strong><br>Punto de partida`).addTo(st.capaVeredas);
    st.mapa.fitBounds(L.featureGroup(grupo).getBounds(), { padding: [10, 10] });
    $("#leyenda").hidden = false;
    actualizarConteo();
    estado(`${d.veredas.length} veredas cargadas. ${sug.size} sugeridas por cercanía.`);
  } catch (e) {
    $("#lista-veredas").innerHTML = `<p class="lista-vacia">No se pudieron cargar las veredas.</p>`;
    $("#mapa-vacio").hidden = false; estado(e.message, true);
  }
}

function seleccionadas() { return [...document.querySelectorAll("#lista-veredas input:checked")].map((i) => i.value); }

function actualizarConteo(conservarEstado = false) {
  const n = seleccionadas().length;
  $("#cont-cand").textContent = n;
  const visitas = +$("#in-visitas").value;
  const ok = n >= Math.max(5, visitas) && n <= 15;
  $("#btn-generar").disabled = !ok;
  if (st.veredas.length && !ok) estado(n > 15 ? "Máximo 15 veredas candidatas." : `Seleccione al menos ${Math.max(5, visitas)} veredas.`, true);
  else if (st.veredas.length && !conservarEstado) estado("");
}

function icono(txt, base = false) {
  const contenido = base ? svg("casa") : esc(txt);
  return L.divIcon({ className: "", html: `<div class="marcador ${base ? "base" : ""}">${contenido}</div>`, iconSize: [30, 30], iconAnchor: [15, 15] });
}

async function generar() {
  ocupado(true); estado("Calculando ruta (distancias reales por carretera)…");
  try {
    const r = await api("/api/rutas", {
      method: "POST",
      body: JSON.stringify({
        municipio: $("#sel-municipio").value,
        candidatas: seleccionadas(),
        visitas: +$("#in-visitas").value,
        alpha: +$("#in-alpha").value / 100,
        tiempo_atencion_min: +$("#in-tiempo").value,
        considerar_equidad: $("#in-equidad").checked,
      }),
    });
    pintarResultado(r);
    estado("Ruta generada y registrada en auditoría.", "ok");
    if (matchMedia("(max-width: 900px)").matches) $("#resultado").scrollIntoView({ behavior: "smooth", block: "start" });
  } catch (e) { estado(e.message, true); }
  finally { ocupado(false); actualizarConteo(true); }
}

function pintarResultado(r) {
  st.capaRuta.clearLayers();
  L.polyline(r.geometria, { color: "#ffffff", weight: 8, opacity: 0.9 }).addTo(st.capaRuta); // borde para contraste
  L.polyline(r.geometria, { color: "#1d4ed8", weight: 4.5, opacity: 0.95 }).addTo(st.capaRuta);
  for (const p of r.orden_visita) {
    L.marker([p.lat, p.lon], { icon: icono(p.orden), title: p.nombre })
      .bindPopup(`<strong>${p.orden}. ${esc(p.nombre)}</strong><br>${esc(p.motivo)}`).addTo(st.capaRuta);
  }
  st.mapa.fitBounds(L.polyline(r.geometria).getBounds(), { padding: [30, 30] });

  $("#kpi-km").textContent = r.distancia_total_km.toFixed(1);
  $("#kpi-tiempo").textContent = fmtMin(r.tiempo_total_estimado_min);
  $("#kpi-n").textContent = r.orden_visita.length;
  $("#kpi-aud").textContent = `#${r.id_auditoria}`;
  $("#advertencias").innerHTML = r.advertencias.map((a) => `<p class="adv" role="alert">${svg("alerta")}<span>${esc(a)}</span></p>`).join("");
  $("#orden").innerHTML = `
    <li class="extremo"><span class="num base">${svg("casa")}</span><div><strong>${esc(r.base.nombre)}</strong>
      <div class="motivo">Salida del equipo de salud</div></div><span class="tramo"></span></li>` +
    r.orden_visita.map((p) => `
    <li><span class="num">${p.orden}</span>
      <div><strong>${esc(p.nombre)}</strong>
        ${p.perfil ? `<div class="perfil-ml" title="Perfil asignado por el modelo K-Means">Perfil: ${esc(p.perfil)}</div>` : ""}
        <div class="motivo">${esc(p.motivo)}</div></div>
      <div class="tramo"><strong>+${p.tramo_km.toFixed(1)} km</strong> <span class="lleg">llegada ≈ ${fmtMin(p.llegada_estimada_min)}</span></div></li>`).join("") +
    `<li class="extremo"><span class="num base">${svg("casa")}</span><div><strong>Regreso a ${esc(r.base.nombre)}</strong>
      <div class="motivo">Fin de la jornada</div></div><span class="tramo"></span></li>`;
  $("#no-sel").innerHTML = r.no_seleccionadas.length
    ? r.no_seleccionadas.map((n) => `<li><strong>${esc(n.nombre)}</strong>: ${esc(n.motivo)}</li>`).join("")
    : "<li>Todas las candidatas fueron incluidas.</li>";
  $("#fuente").textContent = `Distancias: ${r.fuente_distancias}. Candidatas: ${r.criterio_candidatas}. Parámetro de prioridad α = ${r.parametros.alpha}. Necesidad estimada por modelo de ML (${r.modelo_ml || "fórmula"}).`;
  $("#aviso").textContent = r.aviso;
  $("#resultado").hidden = false;
}

// ---------------------------------------------------------------- auditoria
async function cargarAuditoria() {
  try {
    estado("Cargando…", false, "#aud-estado");
    const filas = await api("/api/auditoria?limite=100");
    $("#aud-filas").innerHTML = filas.map((f) => {
      const p = f.parametros || {};
      const params = f.evento === "RUTA_GENERADA"
        ? `mpio ${esc(p.municipio)} · ${esc(p.visitas)} visitas · α=${esc(p.alpha)}`
        : esc(JSON.stringify(p));
      const res = f.resumen ? `${esc(f.resumen.veredas.join(" → "))} (${esc(f.resumen.distancia_total_km)} km)` : "";
      const ver = `<button class="btn-sec btn-mini" type="button" data-ver="${f.id}" aria-label="Ver detalle del registro ${f.id}">${svg("ojo")}<span>Ver</span></button>`;
      const acc = f.evento === "RUTA_GENERADA"
        ? `${ver}<button class="btn-sec btn-mini" type="button" data-rep="${f.id}" aria-label="Reproducir ruta del registro ${f.id}">${svg("repetir")}<span>Reproducir</span></button>`
        : ver;
      const ev = `<span class="evento ${f.evento === "RUTA_GENERADA" ? "ruta" : ""}">${esc(f.evento.replace(/_/g, " "))}</span>`;
      return `<tr><td class="num-col">${f.id}</td><td class="fecha">${esc(f.ts.replace("T", " ").slice(0, 19))}</td><td>${ev}</td>
        <td>${esc(f.sub || "—")}</td><td>${params}</td><td>${res}</td><td class="acc">${acc}</td></tr>`;
    }).join("") || `<tr class="vacio"><td colspan="7">Sin registros todavía. Genere una ruta para crear el primero.</td></tr>`;
    estado(`${filas.length} registros (más recientes primero).`, false, "#aud-estado");
  } catch (e) { estado(e.message, true, "#aud-estado"); }
}

async function verDetalle(id) {
  const r = await api(`/api/auditoria/${id}`);
  $("#aud-json").textContent = JSON.stringify(r, null, 2);
  $("#aud-detalle").hidden = false; $("#aud-detalle").open = true;
  $("#aud-detalle").scrollIntoView({ behavior: "smooth" });
}

async function reproducir(id) {
  try {
    const r = await api(`/api/auditoria/${id}/reproducir`, { method: "POST" });
    $("#aud-estado").innerHTML = r.coincide
      ? `<span class="ok">${svg("ok")}<span>Ruta #${esc(id)} reproducida: mismo orden y misma distancia (${esc(r.reproducido.distancia_total_km)} km).</span></span>`
      : `<span class="mal">${svg("error")}<span>La reproducción de #${esc(id)} no coincide con el registro.</span></span>`;
  } catch (e) { estado(e.message, true, "#aud-estado"); }
}

async function verificar() {
  try {
    const r = await api("/api/auditoria/verificar");
    $("#aud-estado").innerHTML = r.integra
      ? `<span class="ok">${svg("escudo")}<span>Cadena íntegra: ${esc(r.registros)} registros, ningún registro alterado.</span></span>`
      : `<span class="mal">${svg("alerta")}<span>Cadena alterada a partir del registro #${esc(r.primer_registro_alterado)}.</span></span>`;
  } catch (e) { estado(e.message, true, "#aud-estado"); }
}

// ---------------------------------------------------------------- eventos
function enlazarEventos() {
  $("#btn-ingresar").addEventListener("click", iniciarLogin);
  $("#btn-salir").addEventListener("click", cerrarSesion);
  $("#tab-plan").addEventListener("click", () => seleccionarTab("plan"));
  $("#tab-aud").addEventListener("click", () => seleccionarTab("aud"));
  // teclado en pestañas (patrón ARIA tabs): flechas, Inicio, Fin
  $(".tabs").addEventListener("keydown", (e) => {
    if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(e.key)) return;
    const tabs = [...document.querySelectorAll('.tabs [role="tab"]')].filter((t) => !t.hidden);
    const i = tabs.indexOf(document.activeElement); if (i < 0) return;
    const j = e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1
      : (i + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
    e.preventDefault(); tabs[j].focus(); tabs[j].click();
  });
  $("#sel-municipio").addEventListener("change", (e) => cargarVeredas(e.target.value));
  $("#lista-veredas").addEventListener("change", () => actualizarConteo());
  $("#filtro-veredas").addEventListener("input", (e) => {
    const q = e.target.value.trim().toLowerCase();
    for (const l of document.querySelectorAll("#lista-veredas label")) l.hidden = q && !l.dataset.nombre.includes(q);
  });
  $("#in-visitas").addEventListener("input", (e) => { $("#out-visitas").textContent = e.target.value; actualizarConteo(); });
  $("#in-alpha").addEventListener("input", (e) => { $("#out-alpha").textContent = `${e.target.value}% necesidad`; });
  $("#btn-generar").addEventListener("click", generar);
  $("#btn-verificar").addEventListener("click", verificar);
  $("#btn-refrescar").addEventListener("click", cargarAuditoria);
  $("#aud-filas").addEventListener("click", (e) => {
    const b = e.target.closest("button"); if (!b) return;
    if (b.dataset.ver) verDetalle(b.dataset.ver);
    if (b.dataset.rep) reproducir(b.dataset.rep);
  });
}

(async function inicio() {
  enlazarEventos();
  st.cfg = await (await fetch("/api/config")).json();
  try { await procesarCallback(); } catch (e) { alert(e.message); }
  if (!st.token) { try { const t = sessionStorage.getItem("tok"); if (t) guardarToken(t); } catch (_) {} }
  mostrarVista();
})();
