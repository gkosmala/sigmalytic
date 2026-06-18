class DashboardRegistry:
    def __init__(self):
        self.snapshots = {}

    def save(self, name, payload):
        self.snapshots[name] = payload

    def load(self, name):
        return self.snapshots.get(name)
