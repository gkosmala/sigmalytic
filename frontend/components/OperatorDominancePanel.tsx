
/*
SAVE AS:
frontend/components/OperatorDominancePanel.tsx

Operator Dominance Dashboard Panel
*/

import React from "react";

interface Props {
  odsScore: number;
  operatorTrend: string;
  controlRegime: string;
  institutionalVolume: number;
  retailParticipation: number;
}

export default function OperatorDominancePanel(
  props: Props
) {
  return (
    <div className="border rounded p-4">
      <h2 className="font-semibold mb-4">
        Operator Dominance
      </h2>

      <div className="space-y-2">

        <div>
          ODS Score:
          {" "}
          {props.odsScore}
        </div>

        <div>
          Operator Trend:
          {" "}
          {props.operatorTrend}
        </div>

        <div>
          Control Regime:
          {" "}
          {props.controlRegime}
        </div>

        <div>
          Institutional Volume:
          {" "}
          {props.institutionalVolume}
        </div>

        <div>
          Retail Participation:
          {" "}
          {props.retailParticipation}
        </div>

      </div>
    </div>
  );
}
