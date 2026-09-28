"""Real level, false breakout, and cumulative wave behavior checks."""
from backend.weis_imminent import find_imminent_weis_events, wave_effort_result, sequential_trade_setups


class Waves:
    def evaluate(self, df, symbol=""):
        return {"sot_downwaves": 100, "volume_exhaustion": 100,
                "effort_without_reward": 0, "sot_upwaves": 100,
                "buying_exhaustion": 100, "buying_effort_without_reward": 0}

    def _prepare(self, df):
        return df

    def build_waves(self, df):
        return ([{"dir": -1, "vol": 100, "delta": 2, "end": 101},
                 {"dir": 1, "vol": 100, "delta": 2, "end": 109},
                 {"dir": -1, "vol": 90, "delta": 2, "end": 100}],
                None, None, {"dir": 1, "vol": 25, "delta": 1, "end": 101})


def bars():
    data = [{"t": str(i), "o": 105, "h": 107 + i * .01, "l": 105 - i * .01, "c": 105, "v": 100}
            for i in range(80)]
    for i in (20, 40):
        data[i]["l"] = 100
        data[i]["h"] = 110
    return data


def test_spring_requires_prior_multitouch_level_and_actual_reclaim():
    history = bars()
    history[-1].update({"l": 99, "c": 102, "h": 106})
    events = find_imminent_weis_events("ABC", history, "1Day", weis_engine=Waves())
    assert len(events) == 1 and events[0]["signals"] == ["SPRING"]
    assert events[0]["entry_trigger"] == 106 and events[0]["invalidation"] == 99
    assert events[0]["state"] == "TRIGGERED"
    sequence = events[0]["wave_sequence"]
    assert sequence["before_test"]["completed"][-1]["vol"] == 90
    assert sequence["through_test"]["forming"]["vol"] == 25
    no_reclaim = bars()
    no_reclaim[-1].update({"l": 99, "c": 99.5})
    assert not find_imminent_weis_events("ABC", no_reclaim, "1Day", weis_engine=Waves())
    no_breach = bars()
    no_breach[-1].update({"l": 100.5, "c": 102})
    assert not find_imminent_weis_events("ABC", no_breach, "1Day", weis_engine=Waves())
    one_touch = bars()
    one_touch[40]["l"] = 104.6
    one_touch[-1].update({"l": 99, "c": 102, "h": 106})
    assert not find_imminent_weis_events("ABC", one_touch, "1Day", weis_engine=Waves())


def test_upthrust_requires_resistance_breach_and_close_back_inside():
    history = bars()
    history[-1].update({"h": 111, "c": 108, "l": 104})
    events = find_imminent_weis_events("ABC", history, "1Day", weis_engine=Waves())
    assert len(events) == 1 and events[0]["signals"] == ["UPTHRUST"]
    assert events[0]["entry_trigger"] == 104 and events[0]["invalidation"] == 111


def test_cumulative_wave_effort_result_and_diminished_extreme():
    prior = [{"dir": -1, "vol": 100, "delta": 2, "end": 103},
             {"dir": -1, "vol": 110, "delta": 2, "end": 102}]
    absorbed = wave_effort_result(prior, {"dir": -1, "vol": 200, "delta": .5, "end": 101}, -1)
    assert absorbed["effort_without_result"]
    weak = wave_effort_result(prior, {"dir": -1, "vol": 40, "delta": 1, "end": 101}, -1)
    assert weak["diminished_volume_new_extreme"]
    unchanged = wave_effort_result(prior, {"dir": -1, "vol": 40, "delta": 1, "end": 102}, -1)
    assert not unchanged["diminished_volume_new_extreme"]
    up = [{"dir": 1, "vol": 100, "delta": 2, "end": 108},
          {"dir": 1, "vol": 110, "delta": 2, "end": 109}]
    assert wave_effort_result(up, {"dir": 1, "vol": 40, "delta": 1, "end": 110}, 1)["diminished_volume_new_extreme"]


def test_climax_on_test_bar_is_not_labeled_preceding_climax():
    class TestClimax(Waves):
        def build_waves(self, df):
            earlier = [{"dir": -1, "vol": 100, "delta": 2, "end": 102},
                       {"dir": -1, "vol": 100, "delta": 2, "end": 101}]
            if len(df) == 80:
                return earlier + [{"dir": -1, "vol": 500, "delta": 5, "end": 99}], None, None, None
            return earlier, None, None, None

    history = bars()
    history[-1].update({"l": 99, "c": 102, "h": 106})
    events = find_imminent_weis_events("ABC", history, "1Day", weis_engine=TestClimax())
    assert len(events) == 1
    assert events[0]["preceding_climax"] is False


def test_sequential_screen_accepts_prior_effort_or_exhaustion_and_later_low_volume():
    base = {"side": "Long", "entry_trigger": 100, "invalidation": 98,
            "low_volume_test": True, "wave_volume_ratio": .5}
    observations = [
        {**base, "symbol": "EFFORT", "effort_without_reward_score": 100},
        {**base, "symbol": "EXHAUST", "exhaustion_score": 100},
        {**base, "symbol": "CLIMAX", "preceding_climax": True},
        {**base, "symbol": "NO_PRIOR"},
        {**base, "symbol": "NO_TEST", "effort_without_reward_score": 100,
         "low_volume_test": False, "wave_volume_ratio": 1.2},
    ]
    assert [row["symbol"] for row in sequential_trade_setups(observations)] == [
        "CLIMAX", "EFFORT", "EXHAUST"]
