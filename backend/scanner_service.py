class ScannerService:
    def scan(self, records=None, min_score=50):
        records = records or []
        return [
            r for r in records
            if float(r.get("master_score", 0) or 0) >= min_score
        ]

