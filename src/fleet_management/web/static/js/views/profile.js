import { api, apiOptional } from "../api.js";
import { confirmDialog, formatDate, h, pageHead, roleBadge, toast } from "../ui.js";

const POLICY_VERSION = "1.0";
const CONSENT_SOURCE = "web";

const PURPOSES = [
  ["MARKETING_EMAIL", "Маркетингові листи", "Акції та новини сервісу на вашу пошту."],
  ["OPTIONAL_ANALYTICS", "Аналітика використання", "Знеособлена статистика, що допомагає покращувати сервіс."],
  ["PERSONALIZATION", "Персоналізація", "Рекомендації станцій і авто на основі ваших поїздок."],
];

function consentRow(ctx, [purpose, title, description], current) {
  const granted = current?.status === "GRANTED";
  const toggle = h("input", { type: "checkbox", role: "switch", checked: granted, "aria-label": title });
  toggle.addEventListener("change", async () => {
    toggle.disabled = true;
    const action = toggle.checked ? "grant" : "revoke";
    const json = toggle.checked ? { policy_version: POLICY_VERSION, source: CONSENT_SOURCE } : { source: CONSENT_SOURCE };
    try {
      await api(`/api/users/${ctx.user.id}/consents/${purpose}/${action}`, { method: "POST", json });
      toast(toggle.checked ? "Згоду надано" : "Згоду відкликано", "ok");
    } catch (err) {
      toggle.checked = !toggle.checked;
      toast(err.message, "error");
    } finally {
      toggle.disabled = false;
    }
  });
  return h(
    "label",
    { class: "row", style: "padding:12px 0;border-top:1px solid var(--border);cursor:pointer;flex-wrap:nowrap" },
    h("div", { style: "flex:1" }, h("strong", {}, title), h("p", { class: "muted small" }, description)),
    toggle,
  );
}

async function downloadExport(ctx) {
  const data = await api(`/api/users/${ctx.user.id}/personal-data`);
  const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
  const link = h("a", { href: URL.createObjectURL(blob), download: `fleet-personal-data-${ctx.user.id}.json` });
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(link.href), 1000);
  toast("Файл з вашими даними завантажено", "ok");
}

async function anonymize(ctx) {
  const ok = await confirmDialog(
    "Видалити персональні дані?",
    "Ваше ім'я, email, телефон і дані посвідчення буде безповоротно знеособлено, акаунт вимкнено. Історія оренд залишиться без прив'язки до вас. Цю дію не можна скасувати.",
    { confirmLabel: "Так, видалити", danger: true },
  );
  if (!ok) return;
  await api(`/api/users/${ctx.user.id}/anonymize`, { method: "POST" });
  toast("Дані знеособлено, акаунт закрито", "ok");
  ctx.logout();
}

export async function profileView(root, ctx) {
  const { user } = ctx;
  const [renter, consents] = await Promise.all([
    user.role === "user" ? apiOptional("/me/renter") : null,
    api(`/api/users/${user.id}/consents`),
  ]);
  const current = new Map(consents.current.map((c) => [c.purpose, c]));

  root.append(
    pageHead("Профіль", "Обліковий запис і налаштування приватності"),
    h(
      "div",
      { class: "grid-2" },
      h(
        "div",
        { class: "stack" },
        h(
          "div",
          { class: "card" },
          h("div", { class: "card-head" }, h("h2", {}, "Обліковий запис"), roleBadge(user.role)),
          h(
            "dl",
            { class: "kv" },
            h("dt", {}, "Ім'я"),
            h("dd", {}, user.full_name),
            h("dt", {}, "Email"),
            h("dd", {}, user.email),
            h("dt", {}, "Телефон"),
            h("dd", {}, user.phone ?? "—"),
            h("dt", {}, "З нами з"),
            h("dd", {}, formatDate(user.created_at)),
            user.role === "user" ? [h("dt", {}, "Посвідчення"), h("dd", {}, renter ? renter.license_number : "не додано")] : null,
          ),
        ),
        h(
          "div",
          { class: "card" },
          h("div", { class: "card-head", style: "margin-bottom:4px" }, h("h2", {}, "Згоди на обробку даних")),
          h("p", { class: "muted small", style: "margin-bottom:8px" }, `Політика конфіденційності v${POLICY_VERSION}. Змінити рішення можна будь-коли.`),
          PURPOSES.map((p) => consentRow(ctx, p, current.get(p[0]))),
        ),
      ),
      h(
        "div",
        { class: "stack" },
        h(
          "div",
          { class: "card" },
          h("h2", {}, "Мої дані"),
          h("p", { class: "muted small", style: "margin:8px 0 14px" }, "Отримайте копію всіх персональних даних, які ми зберігаємо (JSON)."),
          h("button", { class: "btn btn-ghost btn-block", type: "button", onclick: () => downloadExport(ctx).catch((e) => toast(e.message, "error")) }, "Завантажити мої дані"),
        ),
        h(
          "div",
          { class: "card", style: "border-color:var(--danger)" },
          h("h2", { style: "color:var(--danger)" }, "Видалення акаунта"),
          h("p", { class: "muted small", style: "margin:8px 0 14px" }, "Безповоротне знеособлення персональних даних і закриття акаунта."),
          h("button", { class: "btn btn-danger btn-block", type: "button", onclick: () => anonymize(ctx).catch((e) => toast(e.message, "error")) }, "Видалити мої дані"),
        ),
      ),
    ),
  );
}
