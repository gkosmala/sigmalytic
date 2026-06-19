"""
SAVE AS:
backend/campaign_engine/nightly_campaign_pipeline.py
"""

from backend.campaign_engine.campaign_state_engine import (
    WyckoffSignals,
    transition_campaign_state,
)


def _load_class(module_path, class_names):
    module = __import__(module_path, fromlist=["*"])

    for name in class_names:
        if hasattr(module, name):
            return getattr(module, name)

    raise ImportError(
        f"No matching class found in {module_path}: {class_names}"
    )


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

    payload["current_state"] = transition.new_state.value

    if "state_enum" in payload:
        payload["state_enum"] = transition.new_state.value

    if "transition_next_state" in payload:
        payload["transition_next_state"] = transition.new_state.value

    if "transition_bias" in payload:
        payload["transition_bias"] = transition.reason

    return payload


class NightlyCampaignPipeline:
    def __init__(self, campaign_store):
        self.store = campaign_store

    def run(self):
        campaigns = self.store.get_active_campaigns()
        results = []

        for campaign in campaigns:
            signals = _build_signals_from_campaign(campaign)

            transition = transition_campaign_state(
                campaign=campaign,
                signals=signals,
                current_price=campaign.get("current_price"),
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
                }
            )

        return {
            "ok": True,
            "campaigns_processed": len(results),
            "results": results,
        }


def run_nightly_campaign_pipeline():
    CampaignStore = _load_class(
        "backend.campaign_engine.campaign_store",
        ["CampaignStore", "CampaignRepository"],
    )

    store = CampaignStore()
    pipeline = NightlyCampaignPipeline(campaign_store=store)

    return pipeline.run()


def run_campaign_pipeline():
    return run_nightly_campaign_pipeline()


def run_nightly_pipeline():
    return run_nightly_campaign_pipeline()


def main():
    return run_nightly_campaign_pipeline()