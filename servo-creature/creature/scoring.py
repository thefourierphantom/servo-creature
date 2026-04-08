
class ScoreSystem:
    def __init__(self, rules):
        self.rules = rules
        self.score = 0
        self.streak = 0

    def reset(self):
        self.score = 0
        self.streak = 0

    def register_hit(self, mode_name):
        mode_rules = self.rules[mode_name]
        self.streak += 1
        self.score += mode_rules["points_per_hit"]
        if self.streak > 1:
            self.score += mode_rules.get("streak_bonus", 0)

    def register_miss(self, mode_name):
        mode_rules = self.rules.get(mode_name, {})
        self.streak = 0
        self.score -= mode_rules.get("penalty_on_miss", 0)
        if self.score < 0:
            self.score = 0

