from intelligence.ranking_engine import RankingEngine

class RankingsService:
    def __init__(self):
        self.ranker = RankingEngine()

    def rank(self, records=None):
        return self.ranker.rank(records or [])

