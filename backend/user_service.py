class UserService:
    def profile(self, user_id=None):
        return {
            "user_id": user_id,
            "status": "active"
        }
