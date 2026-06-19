class NotificationDispatcher:
    def dispatch(self, event):
        return {
            "dispatched": True,
            "event": event
        }

