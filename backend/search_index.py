class SearchIndex:
    def __init__(self):
        self.records = []

    def add_many(self, records):
        self.records.extend(records or [])

    def search(self, query):
        q = str(query or "").lower()
        return [r for r in self.records if q in str(r).lower()]

