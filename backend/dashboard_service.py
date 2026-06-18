class DashboardService:
    def build(self, records=None):
        records = records or []
        return {
            "records": records,
            "count": len(records),
            "status": "ready"
        }
