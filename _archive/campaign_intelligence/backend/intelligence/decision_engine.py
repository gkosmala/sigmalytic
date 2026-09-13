
class DecisionEngine:
    def decide(self, score):
        if score >= 80:
            return "ARMED"
        if score >= 50:
            return "WATCH"
        return "LOCKOUT"

