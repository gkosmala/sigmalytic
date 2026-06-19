
class RankingEngine:
    def rank(self, items):
        return sorted(
            items,
            key=lambda x: x.get("score", 0),
            reverse=True
        )

