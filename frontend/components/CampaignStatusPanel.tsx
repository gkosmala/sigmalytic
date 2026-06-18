import React from "react";

export default function CampaignStatusPanel({ data }: any) {
  return <pre>{JSON.stringify(data, null, 2)}</pre>;
}
