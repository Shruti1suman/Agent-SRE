import { apiRequest } from "./client";

export function listProjects() {
  return apiRequest("/api/projects");
}

export function createProject({ projectName, description }) {
  return apiRequest("/api/projects", {
    method: "POST",
    body: { project_name: projectName, description }
  });
}

export function regenerateProjectKey(projectId, { keyName } = {}) {
  return apiRequest(`/api/projects/${encodeURIComponent(projectId)}/keys`, {
    method: "POST",
    body: { key_name: keyName }
  });
}
