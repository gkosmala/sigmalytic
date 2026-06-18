
/*
SAVE AS:
frontend/components/OpportunityDashboard.tsx

Opportunity Dashboard

Displays projected campaign opportunities.
*/

import React from "react";

export interface OpportunityRow {
  symbol: string;
  ucr_score: number;
  confidence: string;
  conservative_target: number;
  aggressive_target: number;
}

interface Props {
  opportunities: OpportunityRow[];
}

export default function OpportunityDashboard(
  props: Props
) {
  return (
    <div className="border rounded p-4">
      <h2 className="font-semibold mb-4">
        Opportunity Dashboard
      </h2>

      <table className="w-full">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>UCR</th>
            <th>Confidence</th>
            <th>Conservative</th>
            <th>Aggressive</th>
          </tr>
        </thead>

        <tbody>
          {props.opportunities.map(
            (row) => (
              <tr key={row.symbol}>
                <td>{row.symbol}</td>
                <td>{row.ucr_score}</td>
                <td>{row.confidence}</td>
                <td>{row.conservative_target}</td>
                <td>{row.aggressive_target}</td>
              </tr>
            )
          )}
        </tbody>
      </table>
    </div>
  );
}
