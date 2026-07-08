
/*
SAVE AS:
frontend/components/StatusCenter.tsx

Campaign Status Center
*/

import React from "react";

interface Props {
  activeCampaigns: number;
  birthCandidates: number;
  expandingCampaigns: number;
  distributionRisk: number;
}

export default function StatusCenter(
  props: Props
) {
  return (
    <div className="border rounded p-4">
      <h2 className="font-semibold mb-4">
        Status Center
      </h2>

      <div className="space-y-2">

        <div>
          Active Campaigns:
          {" "}
          {props.activeCampaigns}
        </div>

        <div>
          Spark:
          {" "}
          {props.birthCandidates}
        </div>

        <div>
          Expanding Campaigns:
          {" "}
          {props.expandingCampaigns}
        </div>

        <div>
          Distribution Risk:
          {" "}
          {props.distributionRisk}
        </div>

      </div>
    </div>
  );
}


