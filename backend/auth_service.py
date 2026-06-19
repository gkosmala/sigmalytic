class AuthService:
    def authenticate(self, username=None):
        return {
            "authenticated": True,
            "user": username
        }

