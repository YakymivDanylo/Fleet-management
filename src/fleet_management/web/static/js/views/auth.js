import { api } from "../api.js";
import { carIcon, field, h, onSubmit, toast } from "../ui.js";

function authCard(title, subtitle, form, foot) {
  return h(
    "div",
    { class: "auth" },
    h(
      "div",
      { class: "card" },
      h(
        "div",
        { class: "auth-head" },
        h("div", { class: "brand-mark" }, carIcon(24)),
        h("h1", {}, title),
        h("p", {}, subtitle),
      ),
      form,
      h("div", { class: "auth-foot" }, foot),
    ),
  );
}

export async function loginView(root, ctx) {
  const form = onSubmit(
    h(
      "form",
      {},
      field("Email", h("input", { name: "username", type: "email", required: true, autocomplete: "email" })),
      field(
        "Пароль",
        h("input", { name: "password", type: "password", required: true, autocomplete: "current-password" }),
      ),
      h("button", { class: "btn btn-block", type: "submit" }, "Увійти"),
    ),
    async (data) => {
      const token = await api("/auth/login", { method: "POST", form: data });
      await ctx.login(token.access_token);
    },
  );
  root.append(
    authCard("Вхід у Fleet", "Каршеринг зі станціями по місту", form, [
      "Немає акаунта? ",
      h("a", { href: "#/register" }, "Зареєструватися"),
    ]),
  );
}

export async function registerView(root, ctx) {
  const form = onSubmit(
    h(
      "form",
      {},
      field("Повне ім'я", h("input", { name: "full_name", required: true, maxlength: 150, autocomplete: "name" })),
      field("Email", h("input", { name: "email", type: "email", required: true, autocomplete: "email" })),
      field(
        "Телефон",
        h("input", { name: "phone", type: "tel", placeholder: "+380 67 123 45 67", autocomplete: "tel" }),
        "Необов'язково",
      ),
      field(
        "Пароль",
        h("input", {
          name: "password",
          type: "password",
          required: true,
          minlength: 8,
          maxlength: 128,
          autocomplete: "new-password",
        }),
        "Щонайменше 8 символів",
      ),
      h("button", { class: "btn btn-block", type: "submit" }, "Створити акаунт"),
    ),
    async (data) => {
      const payload = { ...data, phone: data.phone.trim() || null };
      await api("/auth/register", { method: "POST", json: payload });
      const token = await api("/auth/login", {
        method: "POST",
        form: { username: data.email, password: data.password },
      });
      toast("Акаунт створено", "ok");
      await ctx.login(token.access_token);
    },
  );
  root.append(
    authCard("Реєстрація", "Створіть акаунт, щоб орендувати авто", form, [
      "Вже маєте акаунт? ",
      h("a", { href: "#/login" }, "Увійти"),
    ]),
  );
}
