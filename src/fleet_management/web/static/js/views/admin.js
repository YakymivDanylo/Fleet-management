import { api, ApiError } from "../api.js";
import {
  field,
  formatDate,
  formatDuration,
  h,
  modal,
  money,
  onSubmit,
  pageHead,
  rentalBadge,
  roleBadge,
  select,
  table,
  toast,
  vehicleBadge,
} from "../ui.js";

function stat(label, value, hint) {
  return h(
    "div",
    { class: "card stat" },
    h("span", { class: "stat-label" }, label),
    h("span", { class: "stat-value" }, value),
    hint ? h("span", { class: "muted small" }, hint) : null,
  );
}

function occupancy(stations, vehicles) {
  const parked = new Map(stations.map((s) => [s.id, 0]));
  const available = new Map(stations.map((s) => [s.id, 0]));
  for (const v of vehicles) {
    if (v.status === "rented" || !parked.has(v.station_id)) continue;
    parked.set(v.station_id, parked.get(v.station_id) + 1);
    if (v.status === "available") available.set(v.station_id, available.get(v.station_id) + 1);
  }
  return { parked, available };
}

function formCard(title, form) {
  return h("div", { class: "card" }, h("div", { class: "card-head" }, h("h2", {}, title)), form);
}

// ---------- dashboard ----------

export async function dashboardView(root) {
  const [summary, stations, vehicles, users, rentals] = await Promise.all([
    api("/rentals/summary"),
    api("/stations"),
    api("/vehicles"),
    api("/admin/users"),
    api("/rentals"),
  ]);
  const byStatus = (status) => vehicles.filter((v) => v.status === status).length;
  const { parked } = occupancy(stations, vehicles);
  const stationsById = new Map(stations.map((s) => [s.id, s]));
  const vehiclesById = new Map(vehicles.map((v) => [v.id, v]));

  root.append(
    pageHead("Огляд автопарку", "Поточний стан станцій, авто та оренд"),
    h(
      "div",
      { class: "grid-stats" },
      stat("Виручка", money(summary.total_revenue), `Завершених оренд: ${summary.completed}`),
      stat("Активні оренди", summary.active, `Скасованих: ${summary.cancelled}`),
      stat("Автомобілі", vehicles.length, `вільні ${byStatus("available")} · в оренді ${byStatus("rented")} · сервіс ${byStatus("maintenance")}`),
      stat("Станції / користувачі", `${stations.length} / ${users.length}`),
    ),
    h(
      "div",
      { class: "grid-2" },
      h(
        "div",
        { class: "card" },
        h("div", { class: "card-head" }, h("h2", {}, "Останні оренди"), h("a", { href: "#/admin/rentals" }, "Усі →")),
        table(
          [
            { label: "#", render: (r) => r.id },
            { label: "Авто", render: (r) => vehiclesById.get(r.vehicle_id)?.license_plate ?? `#${r.vehicle_id}` },
            { label: "Початок", render: (r) => formatDate(r.started_at) },
            { label: "Сума", num: true, render: (r) => money(r.cost) },
            { label: "Статус", render: (r) => rentalBadge(r.status) },
          ],
          rentals.slice(0, 6),
          "Оренд ще не було",
        ),
      ),
      h(
        "div",
        { class: "card stack" },
        h("div", { class: "card-head", style: "margin:0" }, h("h2", {}, "Заповненість станцій")),
        stations.length
          ? stations.map((s) => {
              const pct = s.capacity ? Math.min(100, Math.round((parked.get(s.id) / s.capacity) * 100)) : 0;
              return h(
                "div",
                {},
                h("div", { class: "row small" }, h("span", {}, stationsById.get(s.id).address), h("span", { class: "spacer" }), h("span", { class: "muted" }, `${parked.get(s.id)}/${s.capacity}`)),
                h("div", { class: "meter" }, h("span", { style: `width:${pct}%` })),
              );
            })
          : h("p", { class: "muted" }, "Станцій ще немає"),
      ),
    ),
  );
}

// ---------- stations ----------

export async function adminStationsView(root, ctx) {
  const [stations, vehicles] = await Promise.all([api("/stations"), api("/vehicles")]);
  stations.sort((a, b) => a.id - b.id);
  const { parked, available } = occupancy(stations, vehicles);

  const form = onSubmit(
    h(
      "form",
      {},
      h(
        "div",
        { class: "form-row" },
        field("Адреса", h("input", { name: "address", required: true, maxlength: 200, placeholder: "вул. Шевченка, 1" })),
        field("Місткість", h("input", { name: "capacity", type: "number", required: true, min: 1, max: 1000, value: 10 })),
        h("button", { class: "btn", type: "submit" }, "Додати станцію"),
      ),
    ),
    async (data) => {
      await api("/stations", { method: "POST", json: { address: data.address.trim(), capacity: Number(data.capacity) } });
      toast("Станцію додано", "ok");
      ctx.navigate("/admin/stations");
    },
  );

  root.append(
    pageHead("Станції", `Усього: ${stations.length}`),
    formCard("Нова станція", form),
    h(
      "div",
      { class: "card" },
      table(
        [
          { label: "#", render: (s) => s.id },
          { label: "Адреса", render: (s) => s.address },
          { label: "Місткість", num: true, render: (s) => s.capacity },
          { label: "Зайнято", num: true, render: (s) => parked.get(s.id) },
          { label: "Вільних авто", num: true, render: (s) => available.get(s.id) },
          {
            label: "Заповненість",
            render: (s) => {
              const pct = s.capacity ? Math.min(100, Math.round((parked.get(s.id) / s.capacity) * 100)) : 0;
              return h("div", { class: "meter", style: "width:120px", title: `${pct}%` }, h("span", { style: `width:${pct}%` }));
            },
          },
        ],
        stations,
        "Станцій ще немає — додайте першу.",
      ),
    ),
  );
}

// ---------- vehicles ----------

async function showVehicleState(vehicle) {
  let content;
  try {
    const s = await api(`/vehicles/${vehicle.id}/state`);
    const mapUrl = `https://www.openstreetmap.org/?mlat=${s.latitude}&mlon=${s.longitude}#map=16/${s.latitude}/${s.longitude}`;
    content = h(
      "div",
      { class: "stack" },
      s.degraded ? h("div", { class: "alert alert-warn" }, "Кеш недоступний — дані з бази, можуть бути застарілими.") : null,
      h(
        "dl",
        { class: "kv" },
        h("dt", {}, "Оновлено"),
        h("dd", {}, formatDate(s.recorded_at)),
        h("dt", {}, "Координати"),
        h("dd", {}, h("a", { href: mapUrl, target: "_blank", rel: "noopener" }, `${s.latitude.toFixed(5)}, ${s.longitude.toFixed(5)}`)),
        h("dt", {}, "Пальне / заряд"),
        h("dd", {}, h("div", { class: "row" }, h("div", { class: "meter", style: "width:120px" }, h("span", { style: `width:${Math.round(s.fuel_level)}%` })), `${Math.round(s.fuel_level)}%`)),
        h("dt", {}, "Замок"),
        h("dd", {}, s.is_locked ? "Зачинено" : "Відчинено"),
        h("dt", {}, "Джерело"),
        h("dd", {}, s.source === "cache" ? "Redis (кеш)" : "PostgreSQL"),
      ),
    );
  } catch (err) {
    const text =
      err instanceof ApiError && err.status === 404
        ? "Від цього авто ще не надходила телеметрія."
        : err.message;
    content = h("p", { class: "muted" }, text);
  }
  await modal({ title: `Телеметрія · ${vehicle.license_plate}`, content, actions: [{ label: "Закрити", value: true }] });
}

export async function adminVehiclesView(root, ctx) {
  const [stations, vehicles] = await Promise.all([api("/stations"), api("/vehicles")]);
  vehicles.sort((a, b) => a.id - b.id);
  const stationsById = new Map(stations.map((s) => [s.id, s]));
  const stationOptions = stations.map((s) => [s.id, s.address]);

  const form = onSubmit(
    h(
      "form",
      {},
      h(
        "div",
        { class: "form-row" },
        field("Держномер", h("input", { name: "license_plate", required: true, maxlength: 20, placeholder: "BC1234AA" })),
        field("Модель", h("input", { name: "model", required: true, maxlength: 100, placeholder: "Renault Zoe" })),
        field("Станція", select("station_id", stationOptions)),
        h("button", { class: "btn", type: "submit", disabled: !stations.length }, "Додати авто"),
      ),
    ),
    async (data) => {
      await api("/vehicles", {
        method: "POST",
        json: { license_plate: data.license_plate.trim().toUpperCase(), model: data.model.trim(), station_id: Number(data.station_id) },
      });
      toast("Авто додано", "ok");
      ctx.navigate("/admin/vehicles");
    },
  );

  const statusFilter = select("status", [["", "Усі статуси"], ["available", "Вільні"], ["rented", "В оренді"], ["maintenance", "Обслуговування"]]);
  const stationFilter = select("station", [["", "Усі станції"], ...stationOptions]);
  const tableHost = h("div");
  const renderTable = () => {
    const rows = vehicles.filter(
      (v) => (!statusFilter.value || v.status === statusFilter.value) && (!stationFilter.value || v.station_id === Number(stationFilter.value)),
    );
    tableHost.replaceChildren(
      table(
        [
          { label: "#", render: (v) => v.id },
          { label: "Держномер", render: (v) => h("span", { class: "mono" }, v.license_plate) },
          { label: "Статус", render: (v) => vehicleBadge(v.status) },
          { label: "Модель", render: (v) => v.model },
          { label: "Станція", render: (v) => (v.status === "rented" ? h("span", { class: "muted" }, "в дорозі") : stationsById.get(v.station_id)?.address ?? `#${v.station_id}`) },
          { label: "", sticky: true, render: (v) => h("button", { class: "btn btn-ghost btn-sm", type: "button", onclick: () => showVehicleState(v) }, "Телеметрія") },
        ],
        rows,
        "Немає авто за цими фільтрами",
      ),
    );
  };
  statusFilter.setAttribute("aria-label", "Фільтр за статусом");
  stationFilter.setAttribute("aria-label", "Фільтр за станцією");
  statusFilter.addEventListener("change", renderTable);
  stationFilter.addEventListener("change", renderTable);
  renderTable();

  root.append(
    pageHead("Автомобілі", `Усього: ${vehicles.length}`),
    stations.length ? formCard("Нове авто", form) : h("div", { class: "alert alert-warn" }, "Спершу додайте станцію — авто має бути прив'язане до неї."),
    h("div", { class: "card stack" }, h("div", { class: "row" }, h("div", { style: "width:200px" }, statusFilter), h("div", { style: "width:260px" }, stationFilter)), tableHost),
  );
}

// ---------- rentals ----------

export async function adminRentalsView(root) {
  const [rentals, renters, vehicles, stations] = await Promise.all([
    api("/rentals"),
    api("/renters"),
    api("/vehicles"),
    api("/stations"),
  ]);
  const rentersById = new Map(renters.map((r) => [r.id, r]));
  const vehiclesById = new Map(vehicles.map((v) => [v.id, v]));
  const stationsById = new Map(stations.map((s) => [s.id, s]));
  const stationName = (id) => (id ? stationsById.get(id)?.address ?? `#${id}` : "—");

  const statusFilter = select("status", [["", "Усі"], ["active", "Активні"], ["completed", "Завершені"], ["cancelled", "Скасовані"]]);
  const tableHost = h("div");
  const renderTable = () => {
    const rows = rentals.filter((r) => !statusFilter.value || r.status === statusFilter.value);
    tableHost.replaceChildren(
      table(
        [
          { label: "#", render: (r) => r.id },
          { label: "Орендар", render: (r) => rentersById.get(r.renter_id)?.full_name ?? `#${r.renter_id}` },
          { label: "Авто", render: (r) => vehiclesById.get(r.vehicle_id)?.license_plate ?? `#${r.vehicle_id}` },
          { label: "Маршрут", render: (r) => `${stationName(r.start_station_id)} → ${stationName(r.end_station_id)}` },
          { label: "Початок", render: (r) => formatDate(r.started_at) },
          { label: "Тривалість", render: (r) => formatDuration(r.started_at, r.ended_at ?? new Date()) },
          { label: "Сума", num: true, render: (r) => money(r.cost) },
          { label: "Статус", render: (r) => rentalBadge(r.status) },
        ],
        rows,
        "Оренд немає",
      ),
    );
  };
  statusFilter.setAttribute("aria-label", "Фільтр за статусом");
  statusFilter.addEventListener("change", renderTable);
  renderTable();

  root.append(
    pageHead("Оренди", `Усього: ${rentals.length}`),
    h("div", { class: "card stack" }, h("div", { style: "width:200px" }, statusFilter), tableHost),
  );
}

// ---------- users ----------

export async function adminUsersView(root, ctx) {
  const users = await api("/admin/users");

  const form = onSubmit(
    h(
      "form",
      {},
      h(
        "div",
        { class: "form-row" },
        field("Повне ім'я", h("input", { name: "full_name", required: true, maxlength: 150 })),
        field("Email", h("input", { name: "email", type: "email", required: true })),
        field("Пароль", h("input", { name: "password", type: "password", required: true, minlength: 8, maxlength: 128, autocomplete: "new-password" })),
        h("button", { class: "btn", type: "submit" }, "Створити адміна"),
      ),
    ),
    async (data) => {
      await api("/admin/admins", { method: "POST", json: data });
      toast("Адміністратора створено", "ok");
      ctx.navigate("/admin/users");
    },
  );

  root.append(
    pageHead("Користувачі", `Усього: ${users.length}`),
    formCard("Новий адміністратор", form),
    h(
      "div",
      { class: "card" },
      table(
        [
          { label: "#", render: (u) => u.id },
          { label: "Ім'я", render: (u) => u.full_name },
          { label: "Email", render: (u) => u.email },
          { label: "Телефон", render: (u) => u.phone ?? "—" },
          { label: "Роль", render: (u) => roleBadge(u.role) },
          { label: "Стан", render: (u) => h("span", { class: `badge ${u.is_active ? "badge-ok" : ""}` }, u.is_active ? "Активний" : "Вимкнений") },
          { label: "Зареєстровано", render: (u) => formatDate(u.created_at) },
        ],
        users,
      ),
    ),
  );
}
