
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const getCampaigns = async () =>
  fetch(`${API}/api/campaign/active`).then(r => r.json());

export const getRankings = async () =>
  fetch(`${API}/api/campaign/rankings`).then(r => r.json());

export const getStatus = async () =>
  fetch(`${API}/api/campaign/status`).then(r => r.json());
