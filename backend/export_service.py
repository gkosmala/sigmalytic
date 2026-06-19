class ExportService:
    def export(self, records=None):
        return {
            "exported": len(records or [])
        }

