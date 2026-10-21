// Live fleet map: polls GET /vehicles/positions and glides markers to their new positions.

import { api } from "../api.js";
import { carIcon, formatDate, h, pageHead, parseUtc, vehicleBadge } from "../ui.js";

const POLL_MS = 3000;
const STALE_AFTER_S = 60;
const LEAFLET = {
  css: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.css",
  cssIntegrity: "sha384-c6Rcwz4e4CITMbu/NBmnNS8yN2sC3cUElMEMfP3vqqKFp7GOYaaBBCqmaWBjmkjb",
  js: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.min.js",
  jsIntegrity: "sha384-NElt3Op+9NBMCYaef5HxeJmU4Xeard/Lku8ek6hoPTvYkQPh3zLIrJP7KiRocsxO",
};
const FILTERS = [
  ["all", "Усі"],
  ["rented", "В дорозі"],
  ["available", "Вільні"],
  ["maintenance", "Сервіс"],
];

let leafletPromise = null;

function loadLeaflet() {
  if (window.L) return Promise.resolve(window.L);
  leafletPromise ??= new Promise((resolve, reject) => {
    document.head.append(
      h("link", { rel: "stylesheet", href: LEAFLET.css, integrity: LEAFLET.cssIntegrity, crossorigin: "anonymous" }),
    );
    const script = h("script", { src: LEAFLET.js, integrity: LEAFLET.jsIntegrity, crossorigin: "anonymous" });
    script.addEventListener("load", () => resolve(window.L));
    script.addEventListener("error", () => {
      leafletPromise = null;
      reject(new Error("Не вдалося завантажити бібліотеку карти"));
    });
    document.head.append(script);
  });
  return leafletPromise;
}

function ageSeconds(recordedAt) {
  return Math.max(0, Math.round((Date.now() - parseUtc(recordedAt)) / 1000));
}

function ageText(seconds) {
  if (seconds < 60) return `${seconds} с тому`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} хв тому`;
  return `${Math.floor(seconds / 3600)} год тому`;
}

function bearing(from, to) {
  const dLon = ((to.lng - from.lng) * Math.PI) / 180;
  const lat1 = (from.lat * Math.PI) / 180;
  const lat2 = (to.lat * Math.PI) / 180;
  const y = Math.sin(dLon) * Math.cos(lat2);
  const x = Math.cos(lat1) * Math.sin(lat2) - Math.sin(lat1) * Math.cos(lat2) * Math.cos(dLon);
  return (Math.atan2(y, x) * 180) / Math.PI;
}

function markerElement(position) {
  return h(
    "div",
    { class: `vmark vmark-${position.status}` },
    h("span", { class: "vmark-arrow" }),
    h("span", { class: "vmark-body" }, carIcon(14)),
  );
}

function popupContent(position, stationsById) {
  const station = position.status === "rented" ? null : stationsById.get(position.station_id);
  return h(
    "div",
    { class: "vpopup" },
    h("div", { class: "row" }, h("strong", { class: "mono" }, position.license_plate), vehicleBadge(position.status)),
    h("div", { class: "muted small" }, position.model),
    h(
      "dl",
      { class: "kv small" },
      h("dt", {}, "Пальне"),
      h("dd", {}, `${Math.round(position.fuel_level)}%`),
      h("dt", {}, "Замок"),
      h("dd", {}, position.is_locked ? "Зачинено" : "Відчинено"),
      station ? [h("dt", {}, "Станція"), h("dd", {}, station.address)] : null,
      h("dt", {}, "Сигнал"),
      h("dd", {}, `${formatDate(position.recorded_at)} (${ageText(ageSeconds(position.recorded_at))})`),
    ),
  );
}

export async function fleetMapView(root, ctx) {
  const [L, stations] = await Promise.all([loadLeaflet(), api("/stations")]);
  const stationsById = new Map(stations.map((s) => [s.id, s]));

  const state = {
    positions: [],
    withoutTelemetry: [],
    degraded: false,
    filter: "all",
    query: "",
    selected: null,
    live: true,
    fitted: false,
    updatedAt: null,
  };
  const markers = new Map(); // vehicle_id -> { marker, el, animation }

  // ---------- layout ----------
  const liveDot = h("span", { class: "live-dot" });
  const liveLabel = h("span", {}, "Наживо");
  const liveBtn = h("button", { class: "btn btn-ghost live-toggle", type: "button", "aria-pressed": "true" }, liveDot, liveLabel);
  const fitBtn = h("button", { class: "btn btn-ghost", type: "button" }, "Показати всі");
  const subtitle = h("p");
  const head = pageHead("Карта автопарку", null, liveBtn, fitBtn);
  head.firstChild.append(subtitle);

  const mapEl = h("div", { class: "fleet-map", role: "region", "aria-label": "Карта автомобілів" });
  const notices = h("div", { class: "stack" });
  const search = h("input", { type: "search", placeholder: "Пошук: номер або модель", "aria-label": "Пошук авто" });
  const chips = h("div", { class: "chips", role: "group", "aria-label": "Фільтр за статусом" });
  const list = h("ul", { class: "vlist" });
  const footer = h("p", { class: "muted small" });

  root.append(
    head,
    notices,
    h(
      "div",
      { class: "map-layout" },
      h("div", { class: "card map-card" }, mapEl, legend()),
      h("aside", { class: "card map-side" }, search, chips, list, footer),
    ),
  );

  // ---------- map ----------
  // Created in onMount: Leaflet must measure a container that is already in the DOM.
  let map = null;

  const visible = (p) =>
    (state.filter === "all" || p.status === state.filter) &&
    (!state.query || `${p.license_plate} ${p.model}`.toLowerCase().includes(state.query));

  function glide(entry, to) {
    const from = entry.marker.getLatLng();
    if (from.distanceTo(to) > 2) {
      entry.el.style.setProperty("--heading", `${bearing(from, to)}deg`);
      entry.el.classList.add("moving");
    } else {
      entry.el.classList.remove("moving");
    }
    cancelAnimationFrame(entry.animation);
    const start = performance.now();
    const duration = POLL_MS - 200;
    const step = (now) => {
      const t = Math.min(1, (now - start) / duration);
      entry.marker.setLatLng([from.lat + (to.lat - from.lat) * t, from.lng + (to.lng - from.lng) * t]);
      if (t < 1) entry.animation = requestAnimationFrame(step);
    };
    entry.animation = requestAnimationFrame(step);
  }

  function select(vehicleId, { pan = true } = {}) {
    state.selected = vehicleId;
    const entry = markers.get(vehicleId);
    if (entry) {
      if (pan) map.flyTo(entry.marker.getLatLng(), Math.max(map.getZoom(), 15), { duration: 0.6 });
      entry.marker.openPopup();
    }
    renderList();
  }

  function renderMarkers() {
    const seen = new Set();
    for (const p of state.positions) {
      seen.add(p.vehicle_id);
      const latlng = L.latLng(p.latitude, p.longitude);
      let entry = markers.get(p.vehicle_id);
      if (!entry) {
        const el = markerElement(p);
        const marker = L.marker(latlng, {
          icon: L.divIcon({ html: el, className: "vmark-wrap", iconSize: [30, 30], iconAnchor: [15, 15], popupAnchor: [0, -14] }),
          title: p.license_plate,
          keyboard: true,
        });
        marker.bindPopup(() => popupContent(entry.position, stationsById));
        marker.on("click", () => select(p.vehicle_id, { pan: false }));
        entry = { marker, el, animation: 0, position: p };
        markers.set(p.vehicle_id, entry);
      } else {
        glide(entry, latlng);
      }
      entry.position = p;
      entry.el.className = `vmark vmark-${p.status}${ageSeconds(p.recorded_at) > STALE_AFTER_S ? " stale" : ""}${entry.el.classList.contains("moving") ? " moving" : ""}`;
      if (visible(p)) entry.marker.addTo(map);
      else entry.marker.remove();
      if (entry.marker.isPopupOpen()) entry.marker.setPopupContent(popupContent(p, stationsById));
    }
    for (const [id, entry] of markers) {
      if (!seen.has(id)) {
        entry.marker.remove();
        markers.delete(id);
      }
    }
  }

  function renderChips() {
    const count = (status) => state.positions.filter((p) => status === "all" || p.status === status).length;
    chips.replaceChildren(
      ...FILTERS.map(([value, label]) =>
        h(
          "button",
          {
            type: "button",
            class: `chip${state.filter === value ? " active" : ""}`,
            "aria-pressed": String(state.filter === value),
            onclick: () => {
              state.filter = value;
              renderAll();
            },
          },
          label,
          h("span", { class: "chip-count" }, count(value)),
        ),
      ),
    );
  }

  function renderList() {
    const rows = state.positions.filter(visible);
    list.replaceChildren(
      ...(rows.length
        ? rows.map((p) => {
            const age = ageSeconds(p.recorded_at);
            return h(
              "li",
              {},
              h(
                "button",
                {
                  type: "button",
                  class: `vitem${state.selected === p.vehicle_id ? " selected" : ""}`,
                  onclick: () => select(p.vehicle_id),
                },
                h("span", { class: `vdot vdot-${p.status}`, "aria-hidden": "true" }),
                h(
                  "span",
                  { class: "vitem-main" },
                  h("span", { class: "mono" }, p.license_plate),
                  h("span", { class: "muted small" }, p.model),
                ),
                h(
                  "span",
                  { class: "vitem-meta" },
                  h("span", { class: "meter", style: "width:48px", title: `Пальне ${Math.round(p.fuel_level)}%` }, h("span", { style: `width:${Math.round(p.fuel_level)}%` })),
                  h("span", { class: `small ${age > STALE_AFTER_S ? "text-warn" : "muted"}` }, age > STALE_AFTER_S ? "немає сигналу" : ageText(age)),
                ),
              ),
            );
          })
        : [h("li", { class: "empty" }, state.positions.length ? "Нічого не знайдено" : "Ще немає даних телеметрії")]),
    );
  }

  function renderStatus() {
    const moving = state.positions.filter((p) => p.status === "rented").length;
    subtitle.textContent = `${state.positions.length} авто на карті · ${moving} в дорозі${state.updatedAt ? ` · оновлено ${state.updatedAt.toLocaleTimeString("uk-UA")}` : ""}`;
    liveBtn.setAttribute("aria-pressed", String(state.live));
    liveBtn.classList.toggle("paused", !state.live);
    liveLabel.textContent = state.live ? "Наживо" : "Пауза";
    footer.textContent = state.withoutTelemetry.length
      ? `Без телеметрії: ${state.withoutTelemetry.length} авто (не показані на карті)`
      : "";
  }

  function renderAll() {
    renderMarkers();
    renderChips();
    renderList();
    renderStatus();
  }

  let failures = 0;
  async function refresh() {
    try {
      const data = await api("/vehicles/positions");
      Object.assign(state, {
        positions: data.positions,
        withoutTelemetry: data.without_telemetry,
        degraded: data.degraded,
        updatedAt: new Date(),
      });
      failures = 0;
      notices.replaceChildren(
        state.degraded ? h("div", { class: "alert alert-warn" }, "Кеш недоступний — позиції з бази даних, можлива затримка.") : "",
      );
      renderAll();
      if (!state.fitted && state.positions.length) {
        state.fitted = true;
        fitAll();
      }
    } catch (err) {
      failures += 1;
      notices.replaceChildren(h("div", { class: "alert alert-danger" }, `Не вдалося оновити позиції: ${err.message}`));
    }
  }

  function fitAll() {
    const points = state.positions.filter(visible).map((p) => [p.latitude, p.longitude]);
    if (points.length) map.fitBounds(points, { padding: [40, 40], maxZoom: 15 });
  }

  // ---------- polling ----------
  let timer = 0;
  const schedule = () => {
    clearTimeout(timer);
    // Back off while the API keeps failing; stop entirely while paused or hidden.
    if (state.live && !document.hidden) timer = setTimeout(tick, POLL_MS * Math.min(4, 1 + failures));
  };
  const tick = async () => {
    await refresh();
    schedule();
  };
  const onVisibility = () => (document.hidden ? clearTimeout(timer) : tick());

  liveBtn.addEventListener("click", () => {
    state.live = !state.live;
    renderStatus();
    if (state.live) tick();
    else clearTimeout(timer);
  });
  fitBtn.addEventListener("click", fitAll);
  search.addEventListener("input", () => {
    state.query = search.value.trim().toLowerCase();
    renderAll();
  });
  document.addEventListener("visibilitychange", onVisibility);

  ctx.onLeave(() => {
    clearTimeout(timer);
    document.removeEventListener("visibilitychange", onVisibility);
    for (const entry of markers.values()) cancelAnimationFrame(entry.animation);
    map?.remove();
  });

  ctx.onMount(async () => {
    map = L.map(mapEl, { zoomControl: true }).setView([50.4501, 30.5234], 12);
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 19,
      attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a>',
    }).addTo(map);
    await refresh();
    schedule();
  });
}

function legend() {
  return h(
    "div",
    { class: "map-legend small" },
    h("span", {}, h("span", { class: "vdot vdot-rented" }), "В дорозі"),
    h("span", {}, h("span", { class: "vdot vdot-available" }), "Вільне"),
    h("span", {}, h("span", { class: "vdot vdot-maintenance" }), "Сервіс"),
    h("span", {}, h("span", { class: "vdot vdot-stale" }), "Немає сигналу > 1 хв"),
  );
}
