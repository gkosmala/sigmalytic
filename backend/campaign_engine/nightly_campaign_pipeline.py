
"""
SAVE AS:
campaign_engine/nightly_campaign_pipeline.py

Nightly campaign refresh pipeline.

Responsibilities:
- Load active campaigns
- Recalculate scores
- Update states
- Detect decay
- Persist updates
"""

from datetime import datetime


class NightlyCampaignPipeline:

    def __init__(
        self,
        campaign_store,
        scoring_engine,
        transition_engine,
        survival_engine,
    ):
        self.store = campaign_store
        self.scoring = scoring_engine
        self.transition = transition_engine
        self.survival = survival_engine

    def run(self):

        campaigns = self.store.get_active_campaigns()

        results = []

        for campaign in campaigns:

            metrics = {
                "ucr_score": campaign.get(
                    "ucr_score",
                    0,
                ),
                "csd_score": campaign.get(
                    "csd_score",
                    0,
                ),
            }

            new_state = self.transition.evaluate_transition(
                current_state=campaign.get(
                    "campaign_state",
                    "BIRTH",
                ),
                metrics=metrics,
            )

            campaign["campaign_state"] = new_state
            campaign["last_pipeline_run"] = (
                datetime.utcnow().isoformat()
            )

            self.store.save_campaign(
                campaign
            )

            results.append(
                {
                    "campaign_id": campaign.get(
                        "campaign_id"
                    ),
                    "new_state": new_state,
                }
            )

        return {
            "campaigns_processed": len(
                results
            ),
            "results": results,
        }

