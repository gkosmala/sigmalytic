"""
SAVE AS:
backend/campaign_engine/nightly_campaign_pipeline.py
"""

import os

from backend.campaign_engine.campaign_state_engine import (
    WyckoffSignals,
    transition_campaign_state,
)

try:
    from backend.campaign_engine.campaign_discovery_engine import (
        CampaignDiscoveryEngine,
    )
except Exception:
    CampaignDiscoveryEngine = None


def _load_class(module_path, class_names):
    module = __import__(module_path, fromlist=["*"])

    for name in class_names:
        if hasattr(module, name):
            return getattr(module, name)

    raise ImportError(
        f"No matching class found in {module_path}: {class_names}"
    )


def _normalize_symbol_list(symbols=None):
    if not symbols:
        return []

    if isinstance(symbols, str):
        items = symbols.split(",")
    else:
        items = symbols

    cleaned = []

    for item in items:
        value = str(item or "").strip().upper()
        if value:
            cleaned.append(value)

    return cleaned


def _parse_discovery_symbols():
    raw = os.getenv("SIGMALYTIC_DISCOVERY_SYMBOLS", "")
    return _normalize_symbol_list(raw)


def _safe_float(value, default=0.0):
    try:
        if value is None:
            return default
        return float(value)
    except Exception:
        return default


def _hydrate_campaign_evidence(campaign):
    """
    Bridge database schema fields back into the evidence names expected by
    transition_campaign_state().
    """
    hydrated = dict(campaign)

    operator_dominance = _safe_float(hydrated.get("operator_dominance"), 0.0)
    d_score = _safe_float(hydrated.get("d_score"), 0.0)
    obstacle_score = _safe_float(hydrated.get("obstacle_score"), 0.0)
    progress_score = _safe_float(hydrated.get("progress_score"), 0.0)

    hydrated["master_campaign_index"] = _safe_float(
        hydrated.get("master_campaign_index"),
        operator_dominance,
    )
    hydrated["master_survival_score"] = _safe_float(
        hydrated.get("master_survival_score"),
        d_score,
    )
    hydrated["survival_score"] = _safe_float(
        hydrated.get("survival_score"),
        d_score,
    )
    hydrated["birth_score"] = _safe_float(
        hydrated.get("birth_score"),
        max(operator_dominance, obstacle_score, progress_score),
    )
    hydrated["resistance_score"] = _safe_float(
        hydrated.get("resistance_score"),
        obstacle_score,
    )
    hydrated["behavioral_resolution_score"] = _safe_float(
        hydrated.get("behavioral_resolution_score"),
        progress_score,
    )

    hydrated["birth_state"] = hydrated.get("birth_state") or (
        "DISCOVERED" if hydrated["birth_score"] > 0 else "UNKNOWN"
    )
    hydrated["survival_state"] = hydrated.get("survival_state") or (
        "DISCOVERED" if hydrated["master_survival_score"] > 0 else "UNKNOWN"
    )

    return hydrated


def _build_signals_from_campaign(campaign):
    return WyckoffSignals(
        sos_detected=bool(campaign.get("sos_detected", False)),
        jac_detected=bool(campaign.get("jac_detected", False)),
        bu_detected=bool(campaign.get("bu_detected", False)),
        lps_detected=bool(campaign.get("lps_detected", False)),
        choch_detected=bool(campaign.get("choch_detected", False)),
        spring_detected=bool(campaign.get("spring_detected", False)),
        upthrust_detected=bool(campaign.get("upthrust_detected", False)),
        spd=bool(campaign.get("spd", False)),
        dei=bool(campaign.get("dei", False)),
        wed_count=int(campaign.get("wed_count", 0) or 0),
        behavioral_state=str(campaign.get("behavioral_state", "AMBIGUOUS")),
    )


def _safe_update_payload(original_campaign, transition):
    payload = dict(original_campaign)

    payload.pop("campaign_state", None)
    payload.pop("last_pipeline_run", None)
    payload.pop("transition_reason", None)
    payload.pop("transition_confidence", None)

    # Hydrated-only fields are not real columns in campaigns table.
    for key in [
        "birth_score",
        "birth_state",
        "master_campaign_index",
        "master_survival_score",
        "survival_score",
        "survival_state",
        "resistance_score",
        "behavioral_resolution_score",
    ]:
        payload.pop(key, None)

    payload["current_state"] = transition.new_state.value

    if "state_enum" in payload:
        payload["state_enum"] = transition.new_state.value

    if "transition_next_state" in payload:
        payload["transition_next_state"] = transition.new_state.value

    if "transition_bias" in payload:
        payload["transition_bias"] = transition.reason

    return payload


class NightlyCampaignPipeline:
    def __init__(
        self,
        campaign_store,
        symbols=None,
        max_symbols=None,
        bar_limit=None,
        timeframe=None,
    ):
        self.store = campaign_store
        self.symbols = _normalize_symbol_list(symbols)
        self.max_symbols = int(max_symbols) if max_symbols is not None else None
        self.bar_limit = int(bar_limit) if bar_limit is not None else None
        self.timeframe = str(timeframe or "DAILY").upper()

    def _run_discovery_stage(self):
        if CampaignDiscoveryEngine is None:
            return {
                "ok": False,
                "stage": "campaign_discovery",
                "error": "CampaignDiscoveryEngine unavailable",
                "campaigns_discovered": 0,
            }

        try:
            discovery = CampaignDiscoveryEngine(
                store=self.store,
                timeframe=self.timeframe,
                max_symbols=self.max_symbols,
                bar_limit=self.bar_limit,
            )

            symbols = self.symbols or _parse_discovery_symbols()

            if symbols:
                return discovery.run(symbols=symbols, timeframe=self.timeframe)

            return discovery.run(timeframe=self.timeframe)

        except Exception as exc:
            return {
                "ok": False,
                "stage": "campaign_discovery",
                "error": str(exc),
                "campaigns_discovered": 0,
            }

    def run(self):
        discovery_results = self._run_discovery_stage()

        campaigns = self.store.get_active_campaigns()
        results = []

        for campaign in campaigns:
            hydrated_campaign = _hydrate_campaign_evidence(campaign)
            signals = _build_signals_from_campaign(hydrated_campaign)

            transition = transition_campaign_state(
                campaign=hydrated_campaign,
                signals=signals,
                current_price=hydrated_campaign.get("current_price"),
            )

            payload = _safe_update_payload(
                original_campaign=campaign,
                transition=transition,
            )

            self.store.save_campaign(payload)

            results.append(
                {
                    "campaign_id": campaign.get("campaign_id"),
                    "symbol": campaign.get("symbol"),
                    "old_state": transition.old_state.value,
                    "new_state": transition.new_state.value,
                    "changed": transition.changed,
                    "reason": transition.reason,
                    "confidence": transition.confidence,
                    "birth_score": hydrated_campaign.get("birth_score"),
                    "mci": hydrated_campaign.get("master_campaign_index"),
                    "survival": hydrated_campaign.get("master_survival_score"),
                }
            )

        return {
            "ok": True,
            "discovery": discovery_results,
            "campaigns_processed": len(results),
            "results": results,
        }


def run_nightly_campaign_pipeline(
    symbols=None,
    max_symbols=None,
    bar_limit=None,
    timeframe=None,
):
    CampaignStore = _load_class(
        "backend.campaign_engine.campaign_store",
        ["CampaignStore", "CampaignRepository"],
    )

    store = CampaignStore()
    pipeline = NightlyCampaignPipeline(
        campaign_store=store,
        symbols=symbols,
        max_symbols=max_symbols,
        bar_limit=bar_limit,
        timeframe=timeframe,
    )

    return pipeline.run()


def run_campaign_pipeline(
    symbols=None,
    max_symbols=None,
    bar_limit=None,
    timeframe=None,
):
    return run_nightly_campaign_pipeline(
        symbols=symbols,
        max_symbols=max_symbols,
        bar_limit=bar_limit,
        timeframe=timeframe,
    )


def run_nightly_pipeline(
    symbols=None,
    max_symbols=None,
    bar_limit=None,
    timeframe=None,
):
    return run_nightly_campaign_pipeline(
        symbols=symbols,
        max_symbols=max_symbols,
        bar_limit=bar_limit,
        timeframe=timeframe,
    )


def main(
    symbols=None,
    max_symbols=None,
    bar_limit=None,
    timeframe=None,
):
    return run_nightly_campaign_pipeline(
        symbols=symbols,
        max_symbols=max_symbols,
        bar_limit=bar_limit,
        timeframe=timeframe,
    )
