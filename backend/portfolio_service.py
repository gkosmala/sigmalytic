class PortfolioService:
    def summary(self, positions=None):
        positions = positions or []
        total = sum(float(p.get("market_value", 0) or 0) for p in positions)
        return {
            "positions": len(positions),
            "total_market_value": round(total, 2)
        }

