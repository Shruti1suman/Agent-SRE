const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8080";
const TOKEN_KEY = "agentsre.session_token";

export function getStoredToken() {
  return localStorage.getItem(TOKEN_KEY);
}

export function setStoredToken(token) {
  if (token) {
    localStorage.setItem(TOKEN_KEY, token);
  } else {
    localStorage.removeItem(TOKEN_KEY);
  }
}

export async function apiRequest(path, { method = "GET", body, token = getStoredToken(), headers = {} } = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...headers
    },
    body: body === undefined ? undefined : JSON.stringify(body)
  });

  const text = await response.text();
  const data = text ? JSON.parse(text) : null;

  if (!response.ok) {
    const message = errorMessage(data, response.status);
    throw new Error(message);
  }

  return data;
}

function errorMessage(data, status) {
  const detail = data?.detail ?? data?.error;
  if (typeof detail === "string") return detail;
  if (Array.isArray(detail)) {
    return detail
      .map((item) => {
        if (typeof item === "string") return item;
        const location = Array.isArray(item?.loc) ? item.loc.join(".") : "";
        const message = item?.msg || item?.message || JSON.stringify(item);
        if (location === "body.password" && String(message).toLowerCase().includes("at least 1 character")) {
          return "Password is required.";
        }
        if (location === "body.email" && String(message).toLowerCase().includes("valid email")) {
          return "Enter a valid email address.";
        }
        return location ? `${location}: ${message}` : message;
      })
      .filter(Boolean)
      .join("; ");
  }
  if (detail && typeof detail === "object") {
    return detail.message || detail.msg || JSON.stringify(detail);
  }
  if (typeof data === "string") return data;
  return `Request failed with status ${status}`;
}

export { API_BASE_URL };
