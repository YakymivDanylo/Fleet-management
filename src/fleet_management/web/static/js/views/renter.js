import { api, apiOptional } from "../api.js";
import {
  carIcon,
  confirmDialog,
  empty,
  field,
  formatDate,
  formatDuration,
  h,
  modal,
  money,
  onSubmit,
  pageHead,
  rentalBadge,
  table,
  toast,
} from "../ui.js";

// Mirrors rental_service.RATE_PER_HOUR / MIN_BILLABLE_HOURS; shown to the renter before renting.
const TARIFF_TEXT = "5.00 ₴ за кожну розпочату годину, мінімум 1 година";

async function loadFleet() {
  const [stations, vehicles] = await Promise.all([api("/stations"), api("/vehicles")]);
  stations.sort((a, b) => a.id - b.id);
  const byStation = new Map(stations.map((s) => [s.id, { station: s, available: [], parked: 0 }]));
  for (const vehicle of vehicles) {
    const entry = byStation.get(vehicle.station_id);
    if (!entry || vehicle.status === "rented") continue;
    entry.parked += 1;
    if (vehicle.status === "available") entry.available.push(vehicle);
  }
  return { stations, vehicles, byStation };
}

async function loadRenterState() {
  const [renter, rentals] = await Promise.all([apiOptional("/me/renter"), api("/me/rentals")]);
  return { renter, rentals, active: rentals.find((r) => r.status === "active") ?? null };
}

function renterProfileCard(ctx, onDone) {
  const form = onSubmit(
    h(
      "form",
      {},
      h(
        "div",
        { class: "form-row" },
        field("Ім'я як у посвідченні", h("input", { name: "full_name", required: true, maxlength: 150, value: ctx.user.full_name })),
        field("Номер водійського посвідчення", h("input", { name: "license_number", required: true, maxlength: 50, placeholder: "AAA123456" })),
        h("button", { class: "btn", type: "submit" }, "Зберегти"),
      ),
    ),
    async (data) => {
      await api(`/api/users/${ctx.user.id}/renter-profile`, { method: "POST", json: data });
      toast("Профіль орендаря створено", "ok");
      onDone();
    },
  );
  return h(
    "div",
    { class: "card card-accent" },
    h("div", { class: "card-head" }, h("h2", {}, "Завершіть профіль орендаря")),
    h("p", { class: "muted", style: "margin-bottom:14px" }, "Щоб орендувати авто, додайте дані водійського посвідчення."),
    form,
  );
}

async function endRentalFlow(ctx, rental) {
  const { stations, byStation } = await loadFleet();
  const options = stations.map((s) => {
    const { parked } = byStation.get(s.id);
    const full = parked >= s.capacity;
    return h(
      "option",
      { value: s.id, disabled: full, selected: s.id === rental.start_station_id && !full },
      `${s.address} — вільних місць: ${Math.max(0, s.capacity - parked)}`,
    );
  });
  const picker = h("select", { name: "end_station_id" }, options);
  const ok = await modal({
    title: "Завершити оренду",
    content: h(
      "div",
      { class: "stack" },
      field("Станція повернення", picker),
      h("p", { class: "muted small" }, "Повернути авто можна лише на станцію з вільним місцем."),
    ),
    actions: [
      { label: "Скасувати", value: false, class: "btn-ghost" },
      { label: "Завершити", value: true },
    ],
  });
  if (!ok) return;
  const done = await api(`/rentals/${rental.id}/end`, {
    method: "POST",
    json: { end_station_id: Number(picker.value) },
  });
  toast(`Оренду завершено. До сплати: ${money(done.cost)}`, "ok");
  ctx.navigate("/rentals");
}

function activeRentalCard(ctx, rental, vehicle, stationsById) {
  const station = stationsById.get(rental.start_station_id);
  return h(
    "div",
    { class: "card card-accent" },
    h(
      "div",
      { class: "card-head" },
      h("h2", {}, "Ваша поточна поїздка"),
      rentalBadge(rental.status),
    ),
    h(
      "div",
      { class: "row", style: "gap:32px; align-items:flex-start" },
      h(
        "dl",
        { class: "kv" },
        h("dt", {}, "Авто"),
        h("dd", {}, vehicle ? `${vehicle.model} · ${vehicle.license_plate}` : `#${rental.vehicle_id}`),
        h("dt", {}, "Звідки"),
        h("dd", {}, station?.address ?? `Станція #${rental.start_station_id}`),
        h("dt", {}, "Початок"),
        h("dd", {}, formatDate(rental.started_at)),
      ),
      h("div", { class: "stat" }, h("span", { class: "stat-label" }, "Триває"), h("span", { class: "stat-value" }, formatDuration(rental.started_at))),
      h("div", { class: "stat" }, h("span", { class: "stat-label" }, "Нараховано"), h("span", { class: "stat-value" }, money(rental.cost))),
      h("div", { class: "spacer" }),
      h(
        "button",
        {
          class: "btn",
          type: "button",
          onclick: () => endRentalFlow(ctx, rental).catch((e) => toast(e.message, "error")),
        },
        "Завершити оренду",
      ),
    ),
  );
}

export async function stationsView(root, ctx) {
  const [{ stations, vehicles, byStation }, state] = await Promise.all([loadFleet(), loadRenterState()]);
  const stationsById = new Map(stations.map((s) => [s.id, s]));
  const totalAvailable = [...byStation.values()].reduce((n, e) => n + e.available.length, 0);

  root.append(pageHead("Станції", `Доступно авто зараз: ${totalAvailable}`));

  if (!state.renter) root.append(renterProfileCard(ctx, () => ctx.navigate("/stations")));
  if (state.active) {
    const vehicle = vehicles.find((v) => v.id === state.active.vehicle_id);
    root.append(activeRentalCard(ctx, state.active, vehicle, stationsById));
  }

  if (!stations.length) {
    root.append(h("div", { class: "card" }, empty("Станцій ще немає.")));
    return;
  }

  root.append(
    h(
      "div",
      { class: "grid" },
      stations.map((s) => {
        const { available, parked } = byStation.get(s.id);
        const fill = s.capacity ? Math.min(100, Math.round((parked / s.capacity) * 100)) : 0;
        return h(
          "a",
          { class: "card clickable", href: `#/stations/${s.id}`, style: "text-decoration:none;color:inherit" },
          h("div", { class: "card-head" }, h("h3", {}, s.address), h("span", { class: `badge ${available.length ? "badge-ok" : ""}` }, `${available.length} вільних`)),
          h("div", { class: "meter", title: `Зайнято місць: ${parked}/${s.capacity}` }, h("span", { style: `width:${fill}%` })),
          h("p", { class: "muted small", style: "margin-top:8px" }, `Паркомісць: ${parked}/${s.capacity}`),
        );
      }),
    ),
  );
}

export async function stationView(root, ctx) {
  const id = Number(ctx.params.id);
  const [{ byStation }, state] = await Promise.all([loadFleet(), loadRenterState()]);
  const entry = byStation.get(id);
  if (!entry) {
    root.append(h("div", { class: "alert alert-danger" }, "Станцію не знайдено."));
    return;
  }
  const { station, available, parked } = entry;

  root.append(
    pageHead(
      station.address,
      `Вільних авто: ${available.length} · паркомісць зайнято ${parked}/${station.capacity}`,
      h("a", { class: "btn btn-ghost", href: "#/stations" }, "← Усі станції"),
    ),
  );

  let blocker = null;
  if (!state.renter) blocker = "Спершу заповніть профіль орендаря на сторінці «Станції».";
  else if (state.active) blocker = "У вас вже є активна оренда. Завершіть її, щоб узяти інше авто.";
  if (blocker) root.append(h("div", { class: "alert alert-warn" }, blocker));

  if (!available.length) {
    root.append(h("div", { class: "card" }, empty("На цій станції зараз немає вільних авто.")));
    return;
  }

  const rent = async (vehicle) => {
    const ok = await confirmDialog(
      `Орендувати ${vehicle.model}?`,
      `${vehicle.license_plate} · ${station.address}. Тариф: ${TARIFF_TEXT}.`,
      { confirmLabel: "Орендувати" },
    );
    if (!ok) return;
    await api("/rentals/start", {
      method: "POST",
      json: { renter_id: state.renter.id, vehicle_id: vehicle.id },
    });
    toast("Авто ваше! Гарної поїздки.", "ok");
    ctx.navigate("/rentals");
  };

  root.append(
    h(
      "div",
      { class: "grid" },
      available.map((v) =>
        h(
          "div",
          { class: "card" },
          h(
            "div",
            { class: "row", style: "margin-bottom:12px" },
            h("span", { class: "brand-mark" }, carIcon()),
            h("div", {}, h("h3", {}, v.model), h("span", { class: "muted small mono" }, v.license_plate)),
          ),
          h(
            "button",
            {
              class: "btn btn-block",
              type: "button",
              disabled: Boolean(blocker),
              onclick: () => rent(v).catch((e) => toast(e.message, "error")),
            },
            "Орендувати",
          ),
        ),
      ),
    ),
    h("p", { class: "muted small" }, `Тариф: ${TARIFF_TEXT}.`),
  );
}

export async function myRentalsView(root, ctx) {
  const [{ stations, vehicles }, state] = await Promise.all([loadFleet(), loadRenterState()]);
  const stationsById = new Map(stations.map((s) => [s.id, s]));
  const vehiclesById = new Map(vehicles.map((v) => [v.id, v]));
  const completed = state.rentals.filter((r) => r.status === "completed");
  const spent = completed.reduce((sum, r) => sum + (r.cost ?? 0), 0);

  root.append(pageHead("Мої поїздки", `Завершених: ${completed.length} · витрачено ${money(spent)}`));

  if (!state.renter) {
    root.append(renterProfileCard(ctx, () => ctx.navigate("/rentals")));
    return;
  }
  if (state.active) {
    root.append(activeRentalCard(ctx, state.active, vehiclesById.get(state.active.vehicle_id), stationsById));
  }

  const stationName = (id) => (id ? stationsById.get(id)?.address ?? `#${id}` : "—");
  const history = state.rentals.filter((r) => r.status !== "active");
  root.append(
    h(
      "div",
      { class: "card" },
      h("div", { class: "card-head" }, h("h2", {}, "Історія")),
      table(
        [
          { label: "Авто", render: (r) => vehiclesById.get(r.vehicle_id)?.model ?? `#${r.vehicle_id}` },
          { label: "Звідки", render: (r) => stationName(r.start_station_id) },
          { label: "Куди", render: (r) => stationName(r.end_station_id) },
          { label: "Початок", render: (r) => formatDate(r.started_at) },
          { label: "Тривалість", render: (r) => (r.ended_at ? formatDuration(r.started_at, r.ended_at) : "—") },
          { label: "Вартість", num: true, render: (r) => money(r.cost) },
          { label: "Статус", render: (r) => rentalBadge(r.status) },
        ],
        history,
        "Ви ще не здійснили жодної поїздки.",
      ),
    ),
  );
}
