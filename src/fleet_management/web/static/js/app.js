// Hash router + session bootstrap. Each view is `async (root, ctx) => void`.

import { api, session } from "./api.js";
import { h, mount, spinner, toast } from "./ui.js";
import { loginView, registerView } from "./views/auth.js";
import { stationsView, stationView, myRentalsView } from "./views/renter.js";
import {
  dashboardView,
  adminStationsView,
  adminVehiclesView,
  adminRentalsView,
  adminUsersView,
} from "./views/admin.js";
import { fleetMapView } from "./views/map.js";
import { profileView } from "./views/profile.js";

const ROUTES = [
  { path: "/login", view: loginView, public: true },
  { path: "/register", view: registerView, public: true },
  { path: "/stations", view: stationsView, role: "user" },
  { path: "/stations/:id", view: stationView, role: "user" },
  { path: "/rentals", view: myRentalsView, role: "user" },
  { path: "/admin", view: dashboardView, role: "admin" },
  { path: "/admin/map", view: fleetMapView, role: "admin", wide: true },
  { path: "/admin/stations", view: adminStationsView, role: "admin" },
  { path: "/admin/vehicles", view: adminVehiclesView, role: "admin" },
  { path: "/admin/rentals", view: adminRentalsView, role: "admin" },
  { path: "/admin/users", view: adminUsersView, role: "admin" },
  { path: "/profile", view: profileView },
];

const NAV = {
  user: [
    ["/stations", "Станції"],
    ["/rentals", "Мої поїздки"],
    ["/profile", "Профіль"],
  ],
  admin: [
    ["/admin", "Огляд"],
    ["/admin/map", "Карта"],
    ["/admin/stations", "Станції"],
    ["/admin/vehicles", "Автомобілі"],
    ["/admin/rentals", "Оренди"],
    ["/admin/users", "Користувачі"],
    ["/profile", "Профіль"],
  ],
};

const HOME = { user: "/stations", admin: "/admin" };

const ctx = {
  user: null,
  navigate(path) {
    if (location.hash === `#${path}`) render();
    else location.hash = path;
  },
  async login(token) {
    session.save(token);
    ctx.user = await api("/auth/me");
    ctx.navigate(HOME[ctx.user.role]);
  },
  logout() {
    session.clear();
    ctx.user = null;
    ctx.navigate("/login");
  },
};

function match(path) {
  for (const route of ROUTES) {
    const names = [];
    const pattern = route.path.replace(/:(\w+)/g, (_, name) => {
      names.push(name);
      return "([^/]+)";
    });
    const found = path.match(new RegExp(`^${pattern}$`));
    if (found) {
      const params = Object.fromEntries(names.map((n, i) => [n, decodeURIComponent(found[i + 1])]));
      return { route, params };
    }
  }
  return null;
}

function renderChrome(path) {
  const topbar = document.getElementById("topbar");
  topbar.hidden = !ctx.user;
  if (!ctx.user) return;

  document.getElementById("account-name").textContent = ctx.user.full_name;
  const links = NAV[ctx.user.role].map(([href, label]) => {
    // "/admin" must not stay highlighted on "/admin/stations"
    const active = path === href || (href !== "/admin" && path.startsWith(`${href}/`));
    return h("a", { href: `#${href}`, class: active ? "active" : null }, label);
  });
  mount(document.getElementById("nav"), links);
}

let renderSeq = 0;
let cleanups = [];

function leavePage() {
  for (const fn of cleanups.splice(0)) {
    try {
      fn();
    } catch {
      /* a broken cleanup must not block navigation */
    }
  }
}

async function render() {
  const seq = ++renderSeq;
  const root = document.getElementById("app");
  leavePage();
  const path = location.hash.slice(1) || "/";

  if (!ctx.user && session.token) {
    try {
      ctx.user = await api("/auth/me");
    } catch {
      session.clear();
    }
  }

  const found = match(path);
  if (!found) {
    ctx.navigate(ctx.user ? HOME[ctx.user.role] : "/login");
    return;
  }
  const { route, params } = found;
  if (route.public && ctx.user) return ctx.navigate(HOME[ctx.user.role]);
  if (!route.public && !ctx.user) return ctx.navigate("/login");
  if (route.role && route.role !== ctx.user.role) return ctx.navigate(HOME[ctx.user.role]);

  renderChrome(path);
  root.classList.toggle("page-wide", Boolean(route.wide));
  mount(root, spinner());
  try {
    const view = h("div", { class: "stack" });
    const onLeave = (fn) => (seq === renderSeq ? cleanups.push(fn) : fn());
    const mounted = [];
    // For views that need real layout (e.g. a map measuring its container).
    const onMount = (fn) => mounted.push(fn);
    await route.view(view, { ...ctx, params, onLeave, onMount });
    if (seq === renderSeq) {
      mount(root, view);
      root.focus({ preventScroll: true });
      for (const fn of mounted) await fn();
    }
  } catch (err) {
    if (seq !== renderSeq) return;
    mount(
      root,
      h("div", { class: "alert alert-danger" }, `Не вдалося завантажити сторінку: ${err.message}`),
    );
  }
}

window.addEventListener("hashchange", render);
window.addEventListener("session-expired", () => {
  ctx.user = null;
  toast("Сесія завершилась. Увійдіть знову.", "error");
  ctx.navigate("/login");
});
document.getElementById("logout-btn").addEventListener("click", () => ctx.logout());

render();
