
import { useState } from "react";
import { analyzeResearch } from "../services/researchApi";

export function useResearch() {
  const [result, setResult] = useState<any>(null);

  const analyze = async (payload:any) => {
    const data = await analyzeResearch(payload);
    setResult(data);
  };

  return { result, analyze };
}
