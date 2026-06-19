class RankingRegistry:
    def __init__(self):
        self.rankings = {}

    def save(self, name, ranking):
        self.rankings[name] = ranking

    def load(self, name):
        return self.rankings.get(name)

