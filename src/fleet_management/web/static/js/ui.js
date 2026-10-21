// DOM helpers. Everything goes through textContent / attributes, never innerHTML with
// data, so values coming from the API cannot inject markup.

const SVG_NS = "http://www.w3.org/2000/svg";
const SVG_TAGS = new Set(["svg", "path", "circle", "rect", "g"]);

export function h(tag, attrs = {}, ...children) {
  const el = SVG_TAGS.has(tag) ? document.createElementNS(SVG_NS, tag) : document.createElement(tag);
  for (const [key, value] of Object.entries(attrs ?? {})) {
    if (value === undefined || value === null || value === false) continue;
    if (key === "class") el.setAttribute("class", value);
    else if (key === "dataset") Object.assign(el.dataset, value);
    else if (key.startsWith("on") && typeof value === "function") {
      el.addEventListener(key.slice(2).toLowerCase(), value);
    } else if (value === true) el.setAttribute(key, "");
    else el.setAttribute(key, value);
  }
  append(el, children);
  return el;
}

function append(el, children) {
  for (const child of children.flat(Infinity)) {
    if (child === null || child === undefined || child === false) continue;
    el.append(child instanceof Node ? child : document.createTextNode(String(child)));
  }
}

export function carIcon(size = 18) {
  return h(
    "svg",
    { viewBox: "0 0 24 24", width: size, height: size, "aria-hidden": "true" },
    h("path", { d: "M4 15l1.6-5h12.8L20 15v4h-2.5v-1.6h-11V19H4z", fill: "currentColor" }),
  );
}

export function mount(root, ...children) {
  root.replaceChildren();
  append(root, children);
}

export function spinner() {
  return h("div", { class: "spinner", role: "status", "aria-label": "Завантаження" });
}

export function toast(message, kind = "info") {
  const el = h("div", { class: `toast toast-${kind}` }, message);
  const host = document.getElementById("toasts");
  host.append(el);
  while (host.children.length > 3) host.firstElementChild.remove();
  setTimeout(() => el.remove(), kind === "error" ? 6000 : 3500);
}

export function pageHead(title, subtitle, ...actions) {
  return h(
    "div",
    { class: "page-head" },
    h("div", {}, h("h1", {}, title), subtitle ? h("p", {}, subtitle) : null),
    actions.length ? h("div", { class: "row" }, actions) : null,
  );
}

export function empty(text) {
  return h("div", { class: "empty" }, text);
}

export function field(label, input, hint) {
  const id = input.id || `f-${Math.random().toString(36).slice(2, 9)}`;
  input.id = id;
  return h(
    "div",
    { class: "field" },
    h("label", { for: id }, label),
    input,
    hint ? h("span", { class: "hint" }, hint) : null,
  );
}

export function select(name, options, selected) {
  return h(
    "select",
    { name },
    options.map(([value, label]) =>
      h("option", { value, selected: String(value) === String(selected) }, label),
    ),
  );
}

function cellClass(column) {
  return [column.num && "num", column.sticky && "sticky-end"].filter(Boolean).join(" ") || null;
}

export function table(columns, rows, emptyText = "Немає даних") {
  if (!rows.length) return empty(emptyText);
  return h(
    "div",
    { class: "table-wrap responsive" },
    h(
      "table",
      {},
      h("thead", {}, h("tr", {}, columns.map((c) => h("th", { class: cellClass(c) }, c.label)))),
      h(
        "tbody",
        {},
        rows.map((row) =>
          h("tr", {}, columns.map((c) => h("td", { class: cellClass(c), "data-label": c.label || null }, c.render(row)))),
        ),
      ),
    ),
  );
}

// Submits a form through `handler(data)`, disabling the button while the request runs.
export function onSubmit(form, handler) {
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = form.querySelector("button[type=submit]");
    if (button) button.disabled = true;
    try {
      await handler(Object.fromEntries(new FormData(form)));
    } catch (err) {
      toast(err.message, "error");
    } finally {
      if (button) button.disabled = false;
    }
  });
  return form;
}

// Promise-based modal. `content` may be a node; resolves with the clicked action value.
export function modal({ title, content, actions = [{ label: "OK", value: true }] }) {
  return new Promise((resolve) => {
    const close = (value) => {
      backdrop.remove();
      document.removeEventListener("keydown", onKey);
      resolve(value);
    };
    const onKey = (event) => {
      if (event.key === "Escape") close(null);
    };
    const backdrop = h(
      "div",
      { class: "modal-backdrop", onclick: (e) => e.target === backdrop && close(null) },
      h(
        "div",
        { class: "card modal", role: "dialog", "aria-modal": "true", "aria-label": title },
        h("div", { class: "card-head" }, h("h2", {}, title)),
        content,
        h(
          "div",
          { class: "modal-actions" },
          actions.map((a) =>
            h("button", { class: `btn ${a.class ?? ""}`, type: "button", onclick: () => close(a.value) }, a.label),
          ),
        ),
      ),
    );
    document.addEventListener("keydown", onKey);
    document.body.append(backdrop);
    backdrop.querySelector(".modal-actions .btn:last-child")?.focus();
  });
}

export function confirmDialog(title, text, { confirmLabel = "Підтвердити", danger = false } = {}) {
  return modal({
    title,
    content: h("p", { class: "muted" }, text),
    actions: [
      { label: "Скасувати", value: false, class: "btn-ghost" },
      { label: confirmLabel, value: true, class: danger ? "btn-danger" : "" },
    ],
  });
}

// ---------- formatting ----------

const dateFmt = new Intl.DateTimeFormat("uk-UA", { dateStyle: "short", timeStyle: "short" });

// The backend stores rental times as naive UTC; treat strings without an offset as UTC.
export function parseUtc(value) {
  if (!value) return null;
  return new Date(/[zZ]|[+-]\d\d:\d\d$/.test(value) ? value : `${value}Z`);
}

export function formatDate(value) {
  const date = parseUtc(value);
  return date ? dateFmt.format(date) : "—";
}

export function formatDuration(from, to = new Date()) {
  const start = parseUtc(from);
  const end = to instanceof Date ? to : parseUtc(to);
  const minutes = Math.max(0, Math.floor((end - start) / 60000));
  const hours = Math.floor(minutes / 60);
  return hours ? `${hours} год ${minutes % 60} хв` : `${minutes} хв`;
}

export function money(value) {
  if (value === null || value === undefined) return "—";
  return `${Number(value).toFixed(2)} ₴`;
}

const VEHICLE_STATUS = {
  available: ["Вільне", "badge-ok"],
  rented: ["В оренді", "badge-info"],
  maintenance: ["Обслуговування", "badge-warn"],
};
const RENTAL_STATUS = {
  active: ["Активна", "badge-info"],
  completed: ["Завершена", "badge-ok"],
  cancelled: ["Скасована", "badge-danger"],
};

function badgeFrom(map, value) {
  const [label, cls] = map[value] ?? [value, ""];
  return h("span", { class: `badge ${cls}` }, label);
}

export const vehicleBadge = (status) => badgeFrom(VEHICLE_STATUS, status);
export const rentalBadge = (status) => badgeFrom(RENTAL_STATUS, status);
export const roleBadge = (role) =>
  h("span", { class: `badge ${role === "admin" ? "badge-accent" : ""}` }, role === "admin" ? "Адмін" : "Користувач");
