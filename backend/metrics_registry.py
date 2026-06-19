class MetricsRegistry:
    def __init__(self):
        self.metrics = {}

    def set(self, key, value):
        self.metrics[key] = value
        return True

    def get(self, key, default=None):
        return self.metrics.get(key, default)

    def all(self):
        return self.metrics

