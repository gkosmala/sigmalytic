
"""SAVE AS: campaign_engine/renko_engine.py"""

class RenkoEngine:

    def __init__(
        self,
        brick_size: float,
    ):
        self.brick_size = brick_size

    def build(
        self,
        closes,
    ):

        bricks = []

        if not closes:
            return bricks

        last = closes[0]

        for close in closes[1:]:

            while abs(close - last) >= self.brick_size:

                if close > last:
                    last += self.brick_size
                    bricks.append(("UP", last))
                else:
                    last -= self.brick_size
                    bricks.append(("DN", last))

        return bricks

