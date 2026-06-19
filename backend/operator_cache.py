class OperatorCache:
    def __init__(self):
        self.cache = {}

    def put(self, key, value):
        self.cache[key] = value

    def get(self, key):
        return self.cache.get(key)

