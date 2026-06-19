from intelligence.opportunity_builder import OpportunityBuilder

class OpportunitiesService:
    def __init__(self):
        self.builder = OpportunityBuilder()

    def build(self, records=None):
        return self.builder.build(records or [])

