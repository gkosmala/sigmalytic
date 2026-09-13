
class IntelligenceRouter:
    def route(self, payload):
        return {
            "status": "routed",
            "symbol": payload.get("symbol"),
        }

