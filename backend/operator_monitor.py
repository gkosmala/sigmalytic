class OperatorMonitor:
    def monitor(self, record):
        return {
            "symbol": record.get("symbol"),
            "healthy": True
        }
