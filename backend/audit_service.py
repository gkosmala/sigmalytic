class AuditService:
    def audit(self, payload=None):
        return {
            "audit_passed": True,
            "payload_present": payload is not None
        }
