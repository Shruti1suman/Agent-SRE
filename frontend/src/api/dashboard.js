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

export async function fetchDashboardSources(projectId) {
  const params = query({ project_id: projectId });
  const [overview, traces, metrics, incidents, governance, slos] = await Promise.all([
    apiRequest(`/api/overview${params}`),
    apiRequest(`/api/traces${params}`),
    apiRequest(`/api/metrics${params}`),
    apiRequest(`/api/incidents${params}`),
    apiRequest(`/api/governance/overview${params}`),
    apiRequest(`/api/slos${params}`)
  ]);

  return { overview, traces, metrics, incidents, governance, slos };
}

export function fetchTraceReplay(executionId) {
  return apiRequest(`/api/traces/${encodeURIComponent(executionId)}/replay`);
}
