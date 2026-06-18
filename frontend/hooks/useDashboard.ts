
import { useEffect, useState } from "react";
import { getDashboard } from "../services/intelligenceApi";

export function useDashboard() {
  const [data, setData] = useState<any>(null);

  useEffect(() => {
    getDashboard().then(setData);
  }, []);

  return data;
}
