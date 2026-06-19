class SettingsService:
    def load(self):
        return {"loaded": True}

    def save(self, settings):
        return {
            "saved": True,
            "settings": settings
        }

