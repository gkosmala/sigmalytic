from intelligence.intelligence_pipeline import IntelligencePipeline

class IntelligenceService:
    def __init__(self):
        self.pipeline = IntelligencePipeline()

    def evaluate(self, campaign=None, research=None, operator=None):
        return self.pipeline.run(
            campaign=campaign or {},
            research=research or {},
            operator=operator or {}
        )

