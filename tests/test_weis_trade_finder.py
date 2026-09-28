"""Profit-path and structural gating checks for the Sigma Radar trade finder."""
from backend.weis_trade_finder import build_trade_setup, evaluate_trade_path, backtest_symbol


class Structure:
    def _prepare(self, df):
        return df.copy()

    def _find_well_defined_level(self, df, idx, is_support):
        return 100.0 if is_support else 110.0

    def evaluate_bars(self, df, symbol=""):
        return {"verdict": "WATCH", "spring_score": 65.0, "upthrust_score": 0.0,
                "resistance_level": 110.0, "support_level": 100.0}

    def _get_prior_wave_volumes(self, df, idx):
        return {"prior_waves": [1_000_000, 900_000], "current_wave_volume": 200_000}


class Weis:
    def _prepare(self, df):
        return df

    def build_waves(self, df):
        return ([{"dir": -1, "vol": 1_000_000, "delta": 2},
                 {"dir": 1, "vol": 900_000, "delta": 2}], None, None,
                {"vol": 200_000})

    def evaluate(self, df, symbol=""):
        return {"range_is_mature": True, "sot_downwaves": 100.0,
                "volume_exhaustion": 100.0, "effort_without_reward": 0.0,
                "range_support": 100.0, "range_resistance": 110.0,
                "range_support_touches": 3, "range_resistance_touches": 3}


def bars():
    history = [{"t": str(i), "o": 104, "h": 108, "l": 101, "c": 104, "v": 10000}
               for i in range(65)]
    history[-1] = {"t": "65", "o": 100.5, "h": 102, "l": 99, "c": 101, "v": 10000}
    return history


def test_armed_trade_requires_real_structure_and_reward():
    plan = build_trade_setup("ABC", bars(), "1Day", wyckoff_engine=Structure(), weis_engine=Weis())
    assert plan["side"] == "Long" and plan["state"] == "ARMED"
    assert (plan["entry_trigger"], plan["invalidation"], plan["target"]) == (102, 99, 110)
    assert plan["reward_risk"] > 2 and plan["wave_volume_ratio"] < .7
    no_sweep = bars()
    no_sweep[-1]["l"] = 100.5
    assert build_trade_setup("ABC", no_sweep, "1Day", wyckoff_engine=Structure(), weis_engine=Weis()) is None


def test_no_mature_range_means_no_trade():
    class Immature(Weis):
        def evaluate(self, df, symbol=""):
            return {**super().evaluate(df, symbol), "range_is_mature": False}
    assert build_trade_setup("ABC", bars(), "1Day", wyckoff_engine=Structure(), weis_engine=Immature()) is None


def test_profit_path_waits_for_entry_and_resolves_ambiguous_bar_against_trade():
    plan = build_trade_setup("ABC", bars(), "1Day", wyckoff_engine=Structure(), weis_engine=Weis())
    future = [{"o": 101, "h": 101.5, "l": 100, "c": 101},
              {"o": 102, "h": 111, "l": 98, "c": 107}]
    outcome = evaluate_trade_path(plan, future, max_bars=2, cost_bps=5)
    assert outcome["status"] == "STOP_FIRST_OR_AMBIGUOUS"
    assert outcome["net_r"] < -1
    win = evaluate_trade_path(plan, [{"o": 102, "h": 110, "l": 101, "c": 109}], max_bars=2, cost_bps=5)
    assert win["status"] == "TARGET" and win["net_r"] > 2


def test_unfilled_plan_is_not_a_winning_trade():
    plan = build_trade_setup("ABC", bars(), "1Day", wyckoff_engine=Structure(), weis_engine=Weis())
    outcome = evaluate_trade_path(plan, [{"o": 101, "h": 101, "l": 100, "c": 101}], max_bars=1)
    assert outcome == {"status": "NO_ENTRY", "filled": False, "bars_observed": 1}


def test_short_upthrust_uses_resistance_stop_and_lower_support_target():
    class ShortStructure(Structure):
        def evaluate_bars(self, df, symbol=""):
            return {"verdict": "WATCH", "spring_score": 0.0, "upthrust_score": 75.0,
                    "support_level": 90.0, "resistance_level": 110.0}

    class ShortWeis(Weis):
        def evaluate(self, df, symbol=""):
            return {"range_is_mature": True, "sot_upwaves": 100,
                    "range_support": 90.0, "range_resistance": 110.0,
                    "buying_exhaustion": 0, "buying_effort_without_reward": 100}

    test_bars = bars()
    test_bars[-1] = {"t": "65", "o": 109, "h": 111, "l": 107, "c": 108, "v": 10000}
    plan = build_trade_setup("XYZ", test_bars, "1Day",
                             wyckoff_engine=ShortStructure(), weis_engine=ShortWeis())
    assert plan and plan["side"] == "Short"
    assert (plan["entry_trigger"], plan["invalidation"], plan["target"]) == (107, 111, 90)
    win = evaluate_trade_path(plan, [{"o": 107, "h": 109, "l": 89, "c": 91}], max_bars=2)
    assert win["status"] == "TARGET" and win["net_r"] > 4


def test_prior_climax_can_qualify_without_shortening_thrust():
    class Climax(Weis):
        def evaluate(self, df, symbol=""):
            return {"range_is_mature": True, "sot_downwaves": 0,
                    "range_support": 100.0, "range_resistance": 110.0,
                    "volume_exhaustion": 0, "effort_without_reward": 0}

        def build_waves(self, df):
            waves = [{"dir": -1, "vol": 100, "delta": 2},
                     {"dir": -1, "vol": 100, "delta": 2},
                     {"dir": -1, "vol": 250, "delta": 4}]
            return waves, None, None, {"vol": 50}

    plan = build_trade_setup("ABC", bars(), "1Day", wyckoff_engine=Structure(), weis_engine=Climax())
    assert plan and plan["preceding_climax"] is True
    assert "preceding climactic wave" in plan["evidence"]


def test_backtest_uses_only_past_bars_for_setup_and_future_bars_for_profit():
    history = [{"t": str(i), "o": 101, "h": 101, "l": 100, "c": 101, "v": 1000}
               for i in range(70)]
    history[65].update({"o": 102, "h": 110, "l": 101, "c": 108})
    observed_prefixes = []

    def builder(symbol, past, timeframe):
        observed_prefixes.append(len(past))
        return {"symbol": symbol, "side": "Long", "entry_trigger": 102,
                "invalidation": 99, "target": 110} if len(past) == 65 else None

    report = backtest_symbol("ABC", history, "1Day", max_bars=2, cost_bps=5, build=builder)
    assert observed_prefixes[0] == 65
    assert report["completed"] == 1 and report["profitable"] == 1
    assert report["target_first"] == 1 and report["average_modeled_net_r"] > 2
