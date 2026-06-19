class OperatorDominanceService:
    def evaluate(self, ods=None):
        ods = ods or {}
        return {
            "symbol": ods.get("symbol"),
            "ods_score": ods.get("ods_score", 0),
            "control_regime": ods.get("control_regime"),
            "status": "evaluated"
        }

