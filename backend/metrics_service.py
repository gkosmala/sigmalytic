class MetricsService:
    def calculate(self, records=None):
        records = records or []
        return {
            "count": len(records)
        }
