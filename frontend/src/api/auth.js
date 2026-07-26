import { apiRequest, setStoredToken } from "./client";

export async function login({ email, password }) {
  const session = await apiRequest("/api/auth/login", {
    method: "POST",
    body: { email, password },
    token: null
  });
  setStoredToken(session.token);
  return session;
}

export async function signup({ email, password, displayName }) {
  const session = await apiRequest("/api/auth/signup", {
    method: "POST",
    body: { email, password, display_name: displayName },
    token: null
  });
  setStoredToken(session.token);
  return session;
}

export function logout() {
  return apiRequest("/api/auth/logout", { method: "POST" }).finally(() => setStoredToken(null));
}

export function me() {
  return apiRequest("/api/auth/me");
}
