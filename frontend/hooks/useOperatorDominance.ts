
import { useState } from "react";
import { calculateODS } from "../services/operatorDominanceApi";

export function useOperatorDominance() {

  const [data, setData] = useState<any>(null);

  const calculate = async(payload:any) => {
    const result = await calculateODS(payload);
    setData(result);
  };

  return { data, calculate };
}
