from intelligence.campaign_fusion_engine import CampaignFusionEngine
from intelligence.research_fusion_engine import ResearchFusionEngine
from intelligence.operator_fusion_engine import OperatorFusionEngine
from intelligence.signal_fusion_engine import SignalFusionEngine
from intelligence.confluence_engine import ConfluenceEngine
from intelligence.master_scoring_engine import MasterScoringEngine
from intelligence.master_decision_engine import MasterDecisionEngine


class IntelligencePipeline:
    """
    Master V2 intelligence pipeline.
    """

    def __init__(self):
        self.campaign_fusion = CampaignFusionEngine()
        self.research_fusion = ResearchFusionEngine()
        self.operator_fusion = OperatorFusionEngine()
        self.signal_fusion = SignalFusionEngine()
        self.confluence = ConfluenceEngine()
        self.scoring = MasterScoringEngine()
        self.decision = MasterDecisionEngine()

    def run(self, campaign=None, research=None, operator=None):
        campaign_signal = self.campaign_fusion.fuse(campaign or {})
        research_signal = self.research_fusion.fuse(research or {})
        operator_signal = self.operator_fusion.fuse(operator or {})

        fused = self.signal_fusion.fuse(
            campaign=campaign_signal,
            research=research_signal,
            operator=operator_signal,
        )

        confluence = self.confluence.calculate(
            spd=research_signal.get("spd", False),
            dei=research_signal.get("dei", False),
            wed_depth=research_signal.get("wed", 0),
            mta_score=(research_signal.get("mta") or {}).get("mta_score", 0),
            ods_score=operator_signal.get("ods_score", 0),
        )

        score = self.scoring.score({
            "mta_score": (research_signal.get("mta") or {}).get("mta_score", 0),
            "ods_score": operator_signal.get("ods_score", 0),
            "wwe_ratio": research_signal.get("wwe_ratio", 0),
            "csd_score": campaign_signal.get("csd_score", 0),
        })

        decision = self.decision.decide(
            score=score["master_score"],
            distribution_risk=campaign_signal.get("campaign_state") == "DISTRIBUTION_RISK",
        )

        return {
            "campaign": campaign_signal,
            "research": research_signal,
            "operator": operator_signal,
            "fused": fused,
            "confluence": confluence,
            "score": score,
            "decision": decision,
        }

