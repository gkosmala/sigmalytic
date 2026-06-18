
/*
SAVE AS:
frontend/components/CampaignRankings.tsx

Renders UCR-ranked campaign opportunities.
*/

import React from "react";

export interface CampaignRow {
  symbol: string;
  ucr_score: number;
  tier: string;
  campaign_state: string;
}

interface Props {
  campaigns: CampaignRow[];
}

export default function CampaignRankings(
  props: Props
) {
  return (
    <div className="border rounded p-4">
      <h2 className="font-semibold mb-4">
        Campaign Rankings
      </h2>

      <table className="w-full">
        <thead>
          <tr>
            <th>Symbol</th>
            <th>UCR</th>
            <th>Tier</th>
            <th>State</th>
          </tr>
        </thead>

        <tbody>
          {props.campaigns.map(
            (campaign) => (
              <tr
                key={campaign.symbol}
              >
                <td>
                  {campaign.symbol}
                </td>

                <td>
                  {campaign.ucr_score}
                </td>

                <td>
                  {campaign.tier}
                </td>

                <td>
                  {campaign.campaign_state}
                </td>
              </tr>
            )
          )}
        </tbody>
      </table>
    </div>
  );
}
