"""
SAVE AS:
backend/campaign_engine/nightly_campaign_pipeline.py
"""

from datetime import datetime


def _load_class(module_path, class_names):
    module = __import__(module_path, fromlist=["*"])
    for name in class_names:
        if hasattr(module, name):
            return getattr(module, name)
    raise ImportError(f"No matching class found in {module_path}: {class_names}")


class NightlyCampaignPipeline:
    def __init__(self, campaign_store, transition_engine):
        self.store = campaign_store
        self.transition = transition_engine

    def run(self):
        campaigns = self.store.get_active_campaigns()
        results = []

        for campaign in campaigns:
            metrics = {
                "ucr_score": campaign.get("ucr_score", 0),
                "csd_score": campaign.get("csd_score", 0),
                "ods_score": campaign.get("ods_score", 0),
                "birth_score": campaign.get("birth_score", 0),
            }

            new_state = self.transition.evaluate_transition(
                current_state=campaign.get("campaign_state", "BIRTH"),
                metrics=metrics,
            )

            campaign["campaign_state"] = new_state
            campaign["last_pipeline_run"] = datetime.utcnow().isoformat()

            self.store.save_campaign(campaign)

            results.append(
                {
                    "campaign_id": campaign.get("campaign_id"),
                    "symbol": campaign.get("symbol"),
                    "new_state": new_state,
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

    TransitionEngine = _load_class(
        "backend.campaign_engine.campaign_state_engine",
        ["CampaignStateEngine", "StateTransitionEngine"],
    )

    store = CampaignStore()
    transition_engine = TransitionEngine()

    pipeline = NightlyCampaignPipeline(
        campaign_store=store,
        transition_engine=transition_engine,
    )

    return pipeline.run()


def run_campaign_pipeline():
    return run_nightly_campaign_pipeline()


def run_nightly_pipeline():
    return run_nightly_campaign_pipeline()


def main():
    return run_nightly_campaign_pipeline()