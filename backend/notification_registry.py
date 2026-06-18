class NotificationRegistry:
    def __init__(self):
        self.notifications = {}

    def register(self, key, payload):
        self.notifications[key] = payload
        return True

    def get(self, key):
        return self.notifications.get(key)
