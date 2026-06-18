
const API = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

export const calculateODS = async (payload: any) =>
  fetch(`${API}/api/operator-dominance/calculate`, {
    method: "POST",
    headers: {"Content-Type":"application/json"},
    body: JSON.stringify(payload)
  }).then(r => r.json());
