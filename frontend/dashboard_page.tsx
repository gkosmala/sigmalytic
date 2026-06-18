
/*
SAVE AS:
frontend/dashboard_page.tsx

Sigmalytic V2
React / TypeScript Dashboard
*/

import React from "react";

export default function DashboardPage() {
  return (
    <div className="min-h-screen p-6">
      <h1 className="text-3xl font-bold">
        Sigmalytic V2 Dashboard
      </h1>

      <div className="grid grid-cols-2 gap-4 mt-6">

        <div className="border rounded p-4">
          <h2 className="font-semibold">
            Campaign Rankings
          </h2>
          <p>
            Source:
            /api/intelligence/rankings
          </p>
        </div>

        <div className="border rounded p-4">
          <h2 className="font-semibold">
            Status Center
          </h2>
          <p>
            Source:
            /api/intelligence/status-center
          </p>
        </div>

        <div className="border rounded p-4">
          <h2 className="font-semibold">
            Opportunities
          </h2>
          <p>
            Source:
            /api/intelligence/opportunities
          </p>
        </div>

        <div className="border rounded p-4">
          <h2 className="font-semibold">
            Research Engine
          </h2>
          <p>
            Renko / Weis / SOT
          </p>
        </div>

      </div>
    </div>
  );
}
