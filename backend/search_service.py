class SearchService:
    def search(self, query, records=None):
        records = records or []
        q = str(query).lower()

        return [
            r for r in records
            if q in str(r).lower()
        ]

