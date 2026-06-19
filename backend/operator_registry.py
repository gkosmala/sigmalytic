class OperatorRegistry:
    def __init__(self):
        self.records = {}

    def register(self, symbol, record):
        self.records[symbol] = record

    def get(self, symbol):
        return self.records.get(symbol)

