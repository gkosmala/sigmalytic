
import React, { createContext, useContext, useState } from "react";

const CampaignContext = createContext<any>(null);

export function CampaignProvider({ children }: any) {
  const [campaigns, setCampaigns] = useState<any[]>([]);
  return (
    <CampaignContext.Provider value={{ campaigns, setCampaigns }}>
      {children}
    </CampaignContext.Provider>
  );
}

export function useCampaignContext() {
  return useContext(CampaignContext);
}
