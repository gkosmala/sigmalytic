class ResearchService:
    def evaluate(self, research=None):
        research = research or {}
        return {
            "symbol": research.get("symbol"),
            "spd": research.get("spd", False),
            "dei": research.get("dei", False),
            "wed": research.get("wed", 0),
            "status": "evaluated"
        }
