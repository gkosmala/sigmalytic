
/*
SAVE AS:
frontend/pages/index.tsx

Sigmalytic V2
Main Commercial Dashboard
*/

import React from "react";

import CampaignRankings from "../components/CampaignRankings";
import StatusCenter from "../components/StatusCenter";
import ControlledPersistenceLifecycleStatus from "../components/ControlledPersistenceLifecycleStatus";
import OpportunityDashboard from "../components/OpportunityDashboard";
import RenkoWeisPanel from "../components/RenkoWeisPanel";
import OperatorDominancePanel from "../components/OperatorDominancePanel";

export default function HomePage() {

  return (
    <div className="min-h-screen p-6">

      <h1 className="text-4xl font-bold mb-6">
        Sigmalytic V2
      </h1>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">

        <CampaignRankings
          campaigns={[]}
        />

        <StatusCenter
          activeCampaigns={0}
          birthCandidates={0}
          expandingCampaigns={0}
          distributionRisk={0}
        />
      <ControlledPersistenceLifecycleStatus />

        <OpportunityDashboard
          opportunities={[]}
        />

        <RenkoWeisPanel
          renkoTrend="NEUTRAL"
          wwe={0}
          spd={false}
          dei={false}
          wed={0}
          sotAlert={false}
        />

        <OperatorDominancePanel
          odsScore={0}
          operatorTrend="NEUTRAL"
          controlRegime="NEUTRAL_CONTROL"
          institutionalVolume={0}
          retailParticipation={0}
        />

      </div>

    </div>
  );
}
