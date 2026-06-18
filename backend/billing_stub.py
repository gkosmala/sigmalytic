class BillingStub:
    def get_plan(self, user_id=None):
        return {
            "plan": "elite",
            "status": "active"
        }

    def check_access(self, feature):
        return {
            "feature": feature,
            "allowed": True
        }
