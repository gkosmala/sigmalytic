
import React, { createContext, useContext, useState } from "react";

const OperatorDominanceContext = createContext<any>(null);

export function OperatorDominanceProvider({ children }: any) {
  const [operatorDominance, setOperatorDominance] = useState<any>(null);
  return (
    <OperatorDominanceContext.Provider value={{ operatorDominance, setOperatorDominance }}>
      {children}
    </OperatorDominanceContext.Provider>
  );
}

export function useOperatorDominanceContext() {
  return useContext(OperatorDominanceContext);
}
