
/*
SAVE AS:
frontend/services/intelligenceApi.ts

Sigmalytic V2
Frontend API Service Layer
*/

const API_BASE =
  process.env.NEXT_PUBLIC_API_URL ||
  "http://localhost:8000";

export async function getDashboard() {
  const response = await fetch(
    `${API_BASE}/api/intelligence/dashboard`
  );

  return response.json();
}

export async function getRankings() {
  const response = await fetch(
    `${API_BASE}/api/intelligence/rankings`
  );

  return response.json();
}

export async function getStatusCenter() {
  const response = await fetch(
    `${API_BASE}/api/intelligence/status-center`
  );

  return response.json();
}

export async function getOpportunities() {
  const response = await fetch(
    `${API_BASE}/api/intelligence/opportunities`
  );

  return response.json();
}
