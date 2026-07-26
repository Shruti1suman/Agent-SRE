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

export function fetchGovernanceOverview({ projectId, agentId } = {}) {
  return apiRequest(`/api/governance/overview${query({ project_id: projectId, agent_id: agentId })}`);
}

export function fetchGovernanceExecutions({ projectId, agentId } = {}) {
  return apiRequest(`/api/governance/executions${query({ project_id: projectId, agent_id: agentId })}`);
}
