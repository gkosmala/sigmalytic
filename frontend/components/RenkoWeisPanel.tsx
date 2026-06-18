
/*
SAVE AS:
frontend/components/RenkoWeisPanel.tsx

Renko / Weis Research Panel
*/

import React from "react";

interface Props {
  renkoTrend: string;
  wwe: number;
  spd: boolean;
  dei: boolean;
  wed: number;
  sotAlert: boolean;
}

export default function RenkoWeisPanel(
  props: Props
) {
  return (
    <div className="border rounded p-4">
      <h2 className="font-semibold mb-4">
        Renko / Weis Intelligence
      </h2>

      <div className="space-y-2">

        <div>
          Renko Trend:
          {" "}
          {props.renkoTrend}
        </div>

        <div>
          WWE:
          {" "}
          {props.wwe}
        </div>

        <div>
          SPD:
          {" "}
          {props.spd ? "YES" : "NO"}
        </div>

        <div>
          DEI:
          {" "}
          {props.dei ? "YES" : "NO"}
        </div>

        <div>
          WED:
          {" "}
          {props.wed}
        </div>

        <div>
          SOT Alert:
          {" "}
          {props.sotAlert ? "ACTIVE" : "OFF"}
        </div>

      </div>
    </div>
  );
}
