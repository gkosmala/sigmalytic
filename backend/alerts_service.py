class AlertsService:
    def active_alerts(self):
        return []

    def create_alert(self, payload):
        return {
            "created": True,
            "payload": payload
        }
