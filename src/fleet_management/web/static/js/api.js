// Thin fetch wrapper: attaches the JWT, normalises FastAPI error bodies, drops the
// session on 401 so the router sends the user back to the login screen.

const TOKEN_KEY = "fleet.token";

export const session = {
  get token() {
    try {
      return localStorage.getItem(TOKEN_KEY);
    } catch {
      return null;
    }
  },
  save(token) {
    try {
      localStorage.setItem(TOKEN_KEY, token);
    } catch {
      /* private mode: the session lasts until reload */
    }
  },
  clear() {
    try {
      localStorage.removeItem(TOKEN_KEY);
    } catch {
      /* ignore */
    }
  },
};

export class ApiError extends Error {
  constructor(status, message, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

function errorMessage(status, body) {
  if (!body) return `Помилка сервера (${status})`;
  const { detail } = body;
  if (typeof detail === "string") return detail;
  // 422 from pydantic: a list of {loc, msg}
  if (Array.isArray(detail)) {
    return detail.map((d) => `${d.loc?.slice(1).join(".") || "поле"}: ${d.msg}`).join("; ");
  }
  if (body.reason) return body.reason;
  return `Помилка сервера (${status})`;
}

export async function api(path, { method = "GET", json, form } = {}) {
  const headers = {};
  const token = session.token;
  if (token) headers.Authorization = `Bearer ${token}`;

  let body;
  if (json !== undefined) {
    headers["Content-Type"] = "application/json";
    body = JSON.stringify(json);
  } else if (form) {
    body = new URLSearchParams(form);
  }

  let response;
  try {
    response = await fetch(path, { method, headers, body });
  } catch {
    throw new ApiError(0, "Сервер недоступний. Перевірте з'єднання.");
  }

  const text = await response.text();
  let data = null;
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = text;
    }
  }

  if (!response.ok) {
    if (response.status === 401 && token) {
      session.clear();
      window.dispatchEvent(new Event("session-expired"));
    }
    throw new ApiError(response.status, errorMessage(response.status, data), data);
  }
  return data;
}

// Fetch that resolves to null on 404 instead of throwing: for optional resources.
export async function apiOptional(path) {
  try {
    return await api(path);
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}
