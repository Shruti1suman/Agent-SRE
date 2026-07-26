import { apiRequest } from "./client";

function query(params = {}) {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value !== undefined && value !== null && value !== "") {
      search.set(key, value);
    }
  });
  const text = search.toString();
  return text ? `?${text}` : "";
}

export function updateSlo(projectId, sloId, payload) {
  return apiRequest(`/api/slos/${encodeURIComponent(sloId)}${query({ project_id: projectId })}`, {
    method: "PATCH",
    body: payload,
  });
}

export function fetchSloMetricCatalog() {
  return apiRequest("/api/slos/metrics/catalog");
}

export function createSlo(projectId, payload) {
  return apiRequest(`/api/slos${query({ project_id: projectId })}`, {
    method: "POST",
    body: payload,
  });
}

export function deleteSlo(projectId, sloId) {
  return apiRequest(`/api/slos/${encodeURIComponent(sloId)}${query({ project_id: projectId })}`, {
    method: "DELETE",
  });
}
