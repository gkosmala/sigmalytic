from intelligence.status_center_builder import StatusCenterBuilder

class StatusCenterService:
    def __init__(self):
        self.builder = StatusCenterBuilder()

    def build(self, records=None):
        return self.builder.build(records or [])
