
import { useEffect, useState } from "react";
import { getCampaigns } from "../services/campaignApi";

export function useCampaigns() {
  const [data, setData] = useState<any[]>([]);

  useEffect(() => {
    getCampaigns().then((r) =>
      setData(r.campaigns || [])
    );
  }, []);

  return data;
}
