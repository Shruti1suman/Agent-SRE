import { apiRequest } from "./client";

export function fetchIncidentChat(incidentId) {
  return apiRequest(`/api/incidents/${encodeURIComponent(incidentId)}/chat`);
}

export function fetchIncidentReport(incidentId) {
  return apiRequest(`/api/incidents/${encodeURIComponent(incidentId)}/report`);
}

export function askIncident(incidentId, { message, history = [] }) {
  return apiRequest("/api/incidents/ask", {
    method: "POST",
    body: { incident_id: incidentId, message, history }
  });
}
