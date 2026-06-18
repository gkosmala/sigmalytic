import React from "react";

export default function MetricGrid({ metrics=[] }: any) {
  return <pre>{JSON.stringify(metrics, null, 2)}</pre>;
}
