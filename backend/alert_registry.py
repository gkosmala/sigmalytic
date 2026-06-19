class AlertRegistry:
    def __init__(self):
        self.alerts = {}

    def register(self, key, alert):
        self.alerts[key] = alert
        return True

    def all(self):
        return list(self.alerts.values())

