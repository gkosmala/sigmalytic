import { useEffect, useMemo, useState } from "react";

type LifecycleResponse = {
  ok?: boolean;
  d3e_phase?: string;
  target_table?: string;
  route_status?: string;
  read_only?: boolean;
  read_status?: string;
  read_response_count?: number;
  row_found?: boolean;
  lifecycle_verified?: boolean;
  final_lifecycle_verified?: boolean;
  lifecycle_status?: string;
  final_lifecycle_status?: string;
  inserted_row_id?: number;
  inserted_row_created_at?: string;
  lifecycle_symbol?: string;
  lifecycle_audit_component?: string;
  lifecycle_audit_version?: string;
  lifecycle_operator_control_evidence_audit_status?: string;
  lifecycle_d3d_dry_run_gate_audit_status?: string;
  lifecycle_components?: Record<string, boolean>;
  expected_checks?: Record<string, boolean>;
  writes_to_supabase?: boolean;
  supabase_write_authorized?: boolean;
  persistence_write_authorized?: boolean;
  mutates_campaigns?: boolean;
  executes_d3d?: boolean;
  authorizes_d3d?: boolean;
  operator_control_confirmed?: boolean;
  composite_operator_control_confirmed?: boolean;
  not_a_trade_signal?: boolean;
  touches_stripe?: boolean;
};

const API_BASE = (
  process.env.NEXT_PUBLIC_API_URL ||
  process.env.NEXT_PUBLIC_API_BASE_URL ||
  process.env.NEXT_PUBLIC_BACKEND_URL ||
  "https://sigmalytic-backend.onrender.com"
).replace(/\/$/, "");

const D3E9_ENDPOINT =
  "/api/alerts/read-only/controlled-persistence-final-lifecycle-regression-sweep";

function displayBoolean(value: unknown): string {
  if (value === true) return "True";
  if (value === false) return "False";
  return "Unknown";
}

function statusLabel(data: LifecycleResponse | null, loading: boolean, error: string | null): string {
  if (loading) return "LOADING";
  if (error) return "ERROR";
  if (data?.final_lifecycle_verified === true) return "COMPLETE";
  return "ATTENTION";
}

function guardrailClean(data: LifecycleResponse | null): boolean {
  return (
    data?.writes_to_supabase === false &&
    data?.supabase_write_authorized === false &&
    data?.persistence_write_authorized === false &&
    data?.mutates_campaigns === false &&
    data?.executes_d3d === false &&
    data?.authorizes_d3d === false &&
    data?.operator_control_confirmed === false &&
    data?.composite_operator_control_confirmed === false &&
    data?.not_a_trade_signal === true &&
    data?.touches_stripe === false
  );
}

export default function ControlledPersistenceLifecycleStatus() {
  const [data, setData] = useState<LifecycleResponse | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const endpoint = useMemo(() => `${API_BASE}${D3E9_ENDPOINT}`, []);

  useEffect(() => {
    let cancelled = false;

    async function loadLifecycle() {
      try {
        setLoading(true);
        setError(null);

        const response = await fetch(endpoint, {
          method: "GET",
          headers: { Accept: "application/json" },
        });

        if (!response.ok) {
          throw new Error(`HTTP ${response.status}`);
        }

        const payload = (await response.json()) as LifecycleResponse;

        if (!cancelled) {
          setData(payload);
        }
      } catch (err) {
        if (!cancelled) {
          setError(err instanceof Error ? err.message : "Unknown error");
          setData(null);
        }
      } finally {
        if (!cancelled) {
          setLoading(false);
        }
      }
    }

    loadLifecycle();

    return () => {
      cancelled = true;
    };
  }, [endpoint]);

  const label = statusLabel(data, loading, error);
  const clean = guardrailClean(data);

  const lifecycleRows = [
    ["Phase", data?.d3e_phase],
    ["Final lifecycle verified", displayBoolean(data?.final_lifecycle_verified)],
    ["Lifecycle status", data?.final_lifecycle_status],
    ["Inserted audit row id", data?.inserted_row_id],
    ["Audit symbol", data?.lifecycle_symbol],
    ["Audit version", data?.lifecycle_audit_version],
    ["Operator-control status", data?.lifecycle_operator_control_evidence_audit_status],
    ["D3D status", data?.lifecycle_d3d_dry_run_gate_audit_status],
  ];

  const guardrailRows = [
    ["Writes to Supabase", displayBoolean(data?.writes_to_supabase)],
    ["Campaign mutation", displayBoolean(data?.mutates_campaigns)],
    ["D3D executed", displayBoolean(data?.executes_d3d)],
    ["D3D authorized", displayBoolean(data?.authorizes_d3d)],
    ["Operator control confirmed", displayBoolean(data?.operator_control_confirmed)],
    ["Composite operator control confirmed", displayBoolean(data?.composite_operator_control_confirmed)],
    ["Trade signal", data?.not_a_trade_signal === true ? "False" : "Unknown"],
    ["Stripe touched", displayBoolean(data?.touches_stripe)],
  ];

  return (
    <section
      data-testid="controlled-persistence-lifecycle-status"
      style={{
        border: "1px solid rgba(148, 163, 184, 0.35)",
        borderRadius: "16px",
        padding: "18px",
        margin: "18px 0",
        background: "rgba(15, 23, 42, 0.78)",
        color: "#e5e7eb",
      }}
    >
      <div style={{ display: "flex", justifyContent: "space-between", gap: "16px", alignItems: "center" }}>
        <div>
          <div style={{ fontSize: "12px", letterSpacing: "0.08em", color: "#94a3b8", textTransform: "uppercase" }}>
            Controlled Persistence Lifecycle
          </div>
          <h2 style={{ margin: "6px 0 4px", fontSize: "22px" }}>
            D3E.9 Final Lifecycle Regression Sweep
          </h2>
          <div style={{ color: "#cbd5e1", fontSize: "14px" }}>
            Read-only Status Center display. No write. No campaign mutation. No D3D. No operator-control confirmation. No Stripe.
          </div>
        </div>

        <div
          style={{
            borderRadius: "999px",
            padding: "8px 12px",
            fontWeight: 700,
            background: label === "COMPLETE" ? "rgba(22, 101, 52, 0.35)" : "rgba(127, 29, 29, 0.35)",
            border: label === "COMPLETE" ? "1px solid rgba(34, 197, 94, 0.5)" : "1px solid rgba(248, 113, 113, 0.5)",
          }}
        >
          {label}
        </div>
      </div>

      {error ? (
        <div style={{ marginTop: "14px", color: "#fecaca" }}>
          Unable to load D3E.9 lifecycle endpoint: {error}
        </div>
      ) : null}

      <div style={{ display: "grid", gridTemplateColumns: "repeat(auto-fit, minmax(260px, 1fr))", gap: "14px", marginTop: "16px" }}>
        <div style={{ border: "1px solid rgba(148, 163, 184, 0.2)", borderRadius: "12px", padding: "14px" }}>
          <h3 style={{ margin: "0 0 10px", fontSize: "16px" }}>Lifecycle Proof</h3>
          {lifecycleRows.map(([labelText, value]) => (
            <div key={String(labelText)} style={{ display: "flex", justifyContent: "space-between", gap: "12px", padding: "6px 0", borderTop: "1px solid rgba(148, 163, 184, 0.12)" }}>
              <span style={{ color: "#94a3b8" }}>{labelText}</span>
              <span style={{ textAlign: "right", fontWeight: 600 }}>{String(value ?? (loading ? "Loading" : "Unknown"))}</span>
            </div>
          ))}
        </div>

        <div style={{ border: "1px solid rgba(148, 163, 184, 0.2)", borderRadius: "12px", padding: "14px" }}>
          <h3 style={{ margin: "0 0 10px", fontSize: "16px" }}>Doctrine Guardrails</h3>
          {guardrailRows.map(([labelText, value]) => (
            <div key={String(labelText)} style={{ display: "flex", justifyContent: "space-between", gap: "12px", padding: "6px 0", borderTop: "1px solid rgba(148, 163, 184, 0.12)" }}>
              <span style={{ color: "#94a3b8" }}>{labelText}</span>
              <span style={{ textAlign: "right", fontWeight: 700 }}>{String(value)}</span>
            </div>
          ))}
          <div style={{ marginTop: "12px", fontWeight: 700, color: clean ? "#86efac" : "#fecaca" }}>
            Guardrail status: {loading ? "Loading" : clean ? "Clean" : "Needs review"}
          </div>
        </div>
      </div>
    </section>
  );
}
