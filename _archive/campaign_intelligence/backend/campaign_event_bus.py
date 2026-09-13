class CampaignEventBus:
    def __init__(self):
        self.events = []

    def publish(self, event):
        self.events.append(event)
        return True

    def consume(self):
        events = self.events[:]
        self.events.clear()
        return events

