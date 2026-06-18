import React from "react";

export default function CampaignRankingTable({ rows=[] }: any) {
  return <pre>{JSON.stringify(rows, null, 2)}</pre>;
}
