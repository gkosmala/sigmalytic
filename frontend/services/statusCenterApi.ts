
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const getStatusCenter = async () =>
  fetch(`${API}/api/status-center/dashboard`)
    .then(r => r.json());
