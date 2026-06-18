import React from "react";

export default function IntelligenceSummary({ summary }: any) {
  return <pre>{JSON.stringify(summary, null, 2)}</pre>;
}
