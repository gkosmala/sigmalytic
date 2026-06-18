
import React, { createContext, useContext, useState } from "react";

const ResearchContext = createContext<any>(null);

export function ResearchProvider({ children }: any) {
  const [research, setResearch] = useState<any>(null);
  return (
    <ResearchContext.Provider value={{ research, setResearch }}>
      {children}
    </ResearchContext.Provider>
  );
}

export function useResearchContext() {
  return useContext(ResearchContext);
}
