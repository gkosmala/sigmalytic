"""
Sigmalytic Weis Radar follow-through lifecycle engine.

Purpose
-------
Persist TRIGGERED Weis Radar events across later completed bars and determine
whether the market subsequently CONFIRMS or INVALIDATES the trigger.

The engine is deliberately conservative:
- It never creates synthetic market data.
- It only evaluates completed bars supplied by the existing Radar scanner.
- It never confirms or invalidates on the trigger bar itself.
- It uses explicit, inspectable close-based thresholds derived from the real
  trigger bar (and the real structural level when Breakout/Breakdown provides one).
- If neither threshold is crossed, the event remains TRIGGERED. It is not
  forced into a terminal state.

This module is storage/logic only. The full-universe worker remains the owner
of scanning; Redis remains the shared persistence layer.
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional

WEIS_RADAR_LIFECYCLE_KEY = "weis_radar:lifecycle:v1"
LIFECYCLE_VERSION = 1

ACTIVE_STAGE = "TRIGGERED"
TERMINAL_STAGES = {"CONFIRMED", "INVALIDATED"}

# ADDED (2026-11-06): structural breakouts/breakdowns are watched with no time
# limit. CONFIRMED is not final for them: the event stays open until a later
# completed bar closes back through the broken level, which INVALIDATES it
# (recorded as failed after confirmation). They also start from the bar on
# which the level was actually crossed, not the scan that first noticed them,
# and repeat attempts at the same level are numbered.
WATCH_UNTIL_FAIL_SIGNALS = {"BREAKOUT", "BREAKDOWN"}
ATTEMPT_LEVEL_TOLERANCE = 0.01  # levels within 1% count as the same level

TRIGGER_SIGNALS = {
    "SPRING",
    "UPTHRUST",
    "BREAKOUT",
    "BREAKDOWN",
    "SIGN_OF_STRENGTH",
    "SIGN_OF_WEAKNESS",
}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _clean_symbol(value: Any) -> str:
    return str(value or "").upper().strip()


def _signal_type(hit: dict) -> str:
    return str((hit or {}).get("type") or "").upper().strip()


def _signal_is_trigger(signal: str) -> bool:
    s = str(signal or "").upper().strip()
    return s in TRIGGER_SIGNALS or s.startswith("3BAR_")


def _direction_for_signal(signal: str) -> str:
    s = str(signal or "").upper().strip()
    if (
        s == "SPRING"
        or s == "BREAKOUT"
        or s == "SIGN_OF_STRENGTH"
        or "3BAR_BULL" in s
        or "3BAR_UP" in s
    ):
        return "Bullish"
    if (
        s == "UPTHRUST"
        or s == "BREAKDOWN"
        or s == "SIGN_OF_WEAKNESS"
        or "3BAR_BEAR" in s
        or "3BAR_DOWN" in s
    ):
        return "Bearish"
    return "Neutral"


def _event_label(signal: str) -> str:
    s = str(signal or "").upper().strip()
    labels = {
        "SPRING": "Spring",
        "UPTHRUST": "Upthrust",
        "BREAKOUT": "Structural breakout",
        "BREAKDOWN": "Structural breakdown",
        "SIGN_OF_STRENGTH": "Sign of Strength",
        "SIGN_OF_WEAKNESS": "Sign of Weakness",
    }
    if s.startswith("3BAR_"):
        return "3-bar " + s.replace("3BAR_", "").replace("_", " ").lower()
    return labels.get(s, s.replace("_", " ").title() or "Radar event")


def _float(value: Any) -> Optional[float]:
    try:
        number = float(value)
        return number
    except (TypeError, ValueError):
        return None


def _bar_time(bar: dict) -> str:
    return str((bar or {}).get("t") or (bar or {}).get("date") or "")


def _parse_time(value: Any) -> Optional[datetime]:
    text = str(value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        parsed = datetime.fromisoformat(text)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc)
    except Exception:
        return None


def _is_after(candidate: Any, baseline: Any) -> bool:
    cdt = _parse_time(candidate)
    bdt = _parse_time(baseline)
    if cdt is not None and bdt is not None:
        return cdt > bdt
    return str(candidate or "") > str(baseline or "")


def _event_id(symbol: str, timeframe: str, signal: str, first_seen_bar_time: str) -> str:
    raw = f"{symbol}|{timeframe}|{signal}|{first_seen_bar_time}"
    suffix = hashlib.sha1(raw.encode("utf-8")).hexdigest()[:14]
    return f"{symbol}:{timeframe}:{signal}:{suffix}"


def _load_state(redis_client, key: str = WEIS_RADAR_LIFECYCLE_KEY) -> dict:
    if not redis_client:
        return {
            "version": LIFECYCLE_VERSION,
            "last_scan_id": None,
            "updated_at": None,
            "events": {},
        }
    try:
        raw = redis_client.get(key)
        if not raw:
            raise ValueError("empty")
        state = json.loads(raw)
        if not isinstance(state, dict):
            raise ValueError("not a dict")
        events = state.get("events")
        if not isinstance(events, dict):
            events = {}
        return {
            "version": LIFECYCLE_VERSION,
            "last_scan_id": state.get("last_scan_id"),
            "updated_at": state.get("updated_at"),
            "events": events,
        }
    except Exception:
        return {
            "version": LIFECYCLE_VERSION,
            "last_scan_id": None,
            "updated_at": None,
            "events": {},
        }


def _event_sort_key(event: dict) -> str:
    return str(
        event.get("status_changed_at")
        or event.get("last_evaluated_bar_time")
        or event.get("detected_at")
        or ""
    )


def _snapshot_from_state(state: dict) -> dict:
    events = [
        dict(event)
        for event in (state.get("events") or {}).values()
        if isinstance(event, dict)
    ]
    events.sort(key=_event_sort_key, reverse=True)
    summary = {"TRIGGERED": 0, "CONFIRMED": 0, "INVALIDATED": 0}
    for event in events:
        stage = str(event.get("stage") or "")
        if stage in summary:
            summary[stage] += 1
    return {
        "ok": True,
        "version": LIFECYCLE_VERSION,
        "updated_at": state.get("updated_at"),
        "last_scan_id": state.get("last_scan_id"),
        "summary": summary,
        "events": events,
    }


def get_lifecycle_snapshot(redis_client, key: str = WEIS_RADAR_LIFECYCLE_KEY) -> dict:
    """Read the currently persisted lifecycle state without running a scan."""
    return _snapshot_from_state(_load_state(redis_client, key))


def _is_open(event: dict) -> bool:
    """Still being watched: TRIGGERED, or a CONFIRMED breakout/breakdown that
    has not yet closed back through its level."""
    stage = event.get("stage")
    if stage == ACTIVE_STAGE:
        return True
    return stage == "CONFIRMED" and event.get("signal_type") in WATCH_UNTIL_FAIL_SIGNALS


def _crossing_bar(bars: list, hit: dict) -> Optional[dict]:
    """The completed bar on which a breakout/breakdown crossed its level, from
    the detector's own crossing date. None if that bar is not in `bars`."""
    date = str((hit or {}).get("date") or "").strip()
    if not date:
        return None
    bars = bars or []
    for j in range(len(bars) - 1, -1, -1):
        t = _bar_time(bars[j])
        if t == date or (len(date) == 10 and t[:10] == date):
            return bars[_walk_back_to_true_crossing(bars, j, hit)]
    return None


def _walk_back_to_true_crossing(bars: list, j: int, hit: dict) -> int:
    """The detector only looks back 20 bars, so a stock that has been beyond the
    level longer is reported as crossing exactly 20 bars ago. Walk back through
    earlier closes still beyond the level (same 0.1% rule as the detector) to the
    real crossing bar."""
    level = _float((hit or {}).get("level"))
    signal = _signal_type(hit)
    if not level or signal not in WATCH_UNTIL_FAIL_SIGNALS:
        return j
    def beyond(bar):
        c = _float(bar.get("c"))
        if c is None:
            return False
        return c > level * 1.001 if signal == "BREAKOUT" else c < level * 0.999
    while j > 0 and beyond(bars[j - 1]):
        j -= 1
    return j


class WeisRadarLifecycleTracker:
    """
    One tracker instance is created for each full-universe scan.

    The previous scan id lets the tracker distinguish one continuously-present
    signal from a genuinely new occurrence. A signal that stays present across
    repeated scans does not create duplicate lifecycle events. If it disappears
    for at least one completed scan and later reappears, it may open a new event.
    """

    def __init__(self, redis_client, timeframe: str, scan_id: Optional[str] = None,
                 state_key: str = WEIS_RADAR_LIFECYCLE_KEY):
        self.redis_client = redis_client
        self.timeframe = str(timeframe or "1Day")
        self.scan_id = str(scan_id or _utc_now_iso())
        self.state_key = state_key
        self.state = _load_state(redis_client, state_key)
        self.previous_scan_id = self.state.get("last_scan_id")
        self.events: Dict[str, dict] = self.state.setdefault("events", {})
        self.transitions: List[dict] = []

    def process_symbol(self, symbol: str, bars: list, hits: list) -> None:
        """
        Evaluate already-open events first, then register current trigger hits.

        bars must already be trimmed to completed bars by the Radar scanner.
        """
        symbol = _clean_symbol(symbol)
        if not symbol or not bars:
            return

        self._evaluate_open_events(symbol, bars)

        current_bar = bars[-1]
        current_bar_time = _bar_time(current_bar)
        if not current_bar_time:
            return

        for hit in hits or []:
            if not isinstance(hit, dict):
                continue
            signal = _signal_type(hit)
            if not _signal_is_trigger(signal):
                continue

            if signal in WATCH_UNTIL_FAIL_SIGNALS:
                self._register_crossing(symbol, signal, bars, hit, current_bar)
                continue

            # If the exact condition was continuously present on the immediately
            # preceding universe scan, update that event instead of manufacturing
            # a duplicate every time the same condition remains true.
            continuous = self._latest_event(symbol, signal)
            if (
                continuous
                and self.previous_scan_id
                and continuous.get("last_seen_scan_id") == self.previous_scan_id
            ):
                continuous["last_seen_scan_id"] = self.scan_id
                continuous["last_seen_at"] = _utc_now_iso()
                continuous["last_price"] = _float(current_bar.get("c"))
                continue

            event = self._new_event(
                symbol=symbol,
                signal=signal,
                bar=current_bar,
                hit=hit,
            )
            if event is not None:
                self.events[event["event_id"]] = event

    def _latest_event(self, symbol: str, signal: str) -> Optional[dict]:
        candidates = [
            event
            for event in self.events.values()
            if isinstance(event, dict)
            and event.get("symbol") == symbol
            and event.get("timeframe") == self.timeframe
            and event.get("signal_type") == signal
        ]
        if not candidates:
            return None
        candidates.sort(key=_event_sort_key, reverse=True)
        return candidates[0]

    def _register_crossing(self, symbol: str, signal: str, bars: list, hit: dict, current_bar: dict) -> None:
        """One event per actual crossing. The event id comes from the crossing
        bar, so the same crossing seen on later scans updates its event rather
        than opening a duplicate, and a genuinely new crossing (for example a
        second attempt after a failure) opens a new, numbered event."""
        bar = _crossing_bar(bars, hit) or current_bar
        event_id = _event_id(symbol, self.timeframe, signal, _bar_time(bar))
        existing = self.events.get(event_id)
        if not isinstance(existing, dict):
            # An open event at the same level is the same attempt, for example
            # one recorded before crossing-bar ids existed (keyed to the scan
            # bar that first noticed it). Adopt it rather than duplicate it.
            existing = self._open_event_at_level(symbol, signal, _float(hit.get("level")))
        if isinstance(existing, dict):
            existing["last_seen_scan_id"] = self.scan_id
            existing["last_seen_at"] = _utc_now_iso()
            return
        event = self._new_event(symbol=symbol, signal=signal, bar=bar, hit=hit)
        if event is None:
            return
        event["attempt"] = self._attempt_number(symbol, signal, event.get("structure_level"))
        self._update_progress(event, _float(event.get("trigger_price")))
        self.events[event["event_id"]] = event
        # A crossing first seen some bars after it happened is evaluated
        # against the completed bars since, so its stage is current today.
        self._evaluate_event(event, bars)

    def _open_event_at_level(self, symbol: str, signal: str, level: Optional[float]) -> Optional[dict]:
        if level is None or level <= 0:
            return None
        for event in self.events.values():
            if (isinstance(event, dict) and _is_open(event) and event.get("symbol") == symbol
                    and event.get("timeframe") == self.timeframe and event.get("signal_type") == signal):
                other = _float(event.get("structure_level"))
                if other and abs(other / level - 1.0) <= ATTEMPT_LEVEL_TOLERANCE:
                    return event
        return None

    def _attempt_number(self, symbol: str, signal: str, level: Optional[float]) -> int:
        if level is None or level <= 0:
            return 1
        prior = 0
        for event in self.events.values():
            if not isinstance(event, dict):
                continue
            if (event.get("symbol") != symbol or event.get("timeframe") != self.timeframe
                    or event.get("signal_type") != signal):
                continue
            other = _float(event.get("structure_level"))
            if other and abs(other / level - 1.0) <= ATTEMPT_LEVEL_TOLERANCE:
                prior += 1
        return prior + 1

    def _new_event(self, symbol: str, signal: str, bar: dict, hit: dict) -> Optional[dict]:
        direction = _direction_for_signal(signal)
        if direction not in {"Bullish", "Bearish"}:
            return None

        trigger_time = _bar_time(bar)
        trigger_open = _float(bar.get("o"))
        trigger_high = _float(bar.get("h"))
        trigger_low = _float(bar.get("l"))
        trigger_close = _float(bar.get("c"))
        if trigger_high is None or trigger_low is None or trigger_close is None:
            return None

        structure_level = _float(hit.get("level"))
        supplied_invalidation = _float(hit.get("invalidation"))

        if direction == "Bullish":
            confirmation_level = trigger_high
            invalidation_level = supplied_invalidation if supplied_invalidation is not None else trigger_low
            if signal == "BREAKOUT" and structure_level is not None:
                invalidation_level = structure_level
            confirmation_rule = f"Later completed-bar close above {confirmation_level:.4f}"
            invalidation_rule = f"Later completed-bar close below {invalidation_level:.4f}"
        else:
            confirmation_level = trigger_low
            invalidation_level = supplied_invalidation if supplied_invalidation is not None else trigger_high
            if signal == "BREAKDOWN" and structure_level is not None:
                invalidation_level = structure_level
            confirmation_rule = f"Later completed-bar close below {confirmation_level:.4f}"
            invalidation_rule = f"Later completed-bar close above {invalidation_level:.4f}"

        event_id = _event_id(symbol, self.timeframe, signal, trigger_time)
        now = _utc_now_iso()
        return {
            "event_id": event_id,
            "symbol": symbol,
            "timeframe": self.timeframe,
            "signal_type": signal,
            "event": _event_label(signal),
            "direction": direction,
            "stage": ACTIVE_STAGE,
            "detected_at": now,
            "trigger_bar_time": trigger_time,
            "trigger_open": trigger_open,
            "trigger_high": trigger_high,
            "trigger_low": trigger_low,
            "trigger_price": trigger_close,
            "structure_level": structure_level,
            "confirmation_level": confirmation_level,
            "invalidation_level": invalidation_level,
            "confirmation_rule": confirmation_rule,
            "invalidation_rule": invalidation_rule,
            "score": _float(hit.get("score")),
            "original_hit": dict(hit),
            "last_price": trigger_close,
            "last_evaluated_bar_time": trigger_time,
            "bars_observed_after_trigger": 0,
            "last_seen_scan_id": self.scan_id,
            "last_seen_at": now,
            "status_changed_at": now,
            "reason": "Trigger detected; waiting for a later completed bar.",
        }

    def _evaluate_open_events(self, symbol: str, bars: list) -> None:
        for event in list(self.events.values()):
            if not isinstance(event, dict):
                continue
            if event.get("symbol") != symbol or event.get("timeframe") != self.timeframe:
                continue
            if not _is_open(event):
                continue
            self._evaluate_event(event, bars)

    def _evaluate_event(self, event: dict, bars: list) -> None:
        baseline = event.get("last_evaluated_bar_time") or event.get("trigger_bar_time")
        new_bars = [bar for bar in bars if _bar_time(bar) and _is_after(_bar_time(bar), baseline)]
        if not new_bars:
            return

        direction = event.get("direction")
        confirmation = _float(event.get("confirmation_level"))
        invalidation = _float(event.get("invalidation_level"))
        if direction not in {"Bullish", "Bearish"} or confirmation is None or invalidation is None:
            return
        bullish = direction == "Bullish"
        watch_after_confirm = event.get("signal_type") in WATCH_UNTIL_FAIL_SIGNALS

        for bar in new_bars:
            close = _float(bar.get("c"))
            bar_time = _bar_time(bar)
            if close is None:
                continue

            event["last_price"] = close
            event["last_evaluated_bar_time"] = bar_time
            event["bars_observed_after_trigger"] = int(event.get("bars_observed_after_trigger") or 0) + 1
            if watch_after_confirm:
                self._update_progress(event, close)

            failed = close < invalidation if bullish else close > invalidation
            if failed:
                was_confirmed = event.get("stage") == "CONFIRMED"
                if was_confirmed:
                    event["failed_after_confirmation"] = True
                word = "fell below" if bullish else "rose above"
                self._transition(
                    event,
                    "INVALIDATED",
                    bar_time,
                    close,
                    f"Completed-bar close {close:.4f} {word} invalidation {invalidation:.4f}"
                    + (" after confirmation." if was_confirmed else "."),
                )
                break

            if event.get("stage") == ACTIVE_STAGE:
                confirmed = close > confirmation if bullish else close < confirmation
                if confirmed:
                    word = "exceeded" if bullish else "fell below"
                    event["confirmed_bar_time"] = bar_time
                    event["confirmed_price"] = close
                    self._transition(
                        event,
                        "CONFIRMED",
                        bar_time,
                        close,
                        f"Completed-bar close {close:.4f} {word} confirmation {confirmation:.4f}."
                        + (" Still watched until a close back through the level." if watch_after_confirm else ""),
                    )
                    if not watch_after_confirm:
                        break

    @staticmethod
    def _update_progress(event: dict, close: Optional[float]) -> None:
        """Move since the crossing, and the best close in the break's direction."""
        if close is None:
            return
        bullish = event.get("direction") == "Bullish"
        trigger = _float(event.get("trigger_price"))
        level = _float(event.get("structure_level")) or _float(event.get("invalidation_level"))
        best = _float(event.get("best_close"))
        if best is None or (close > best if bullish else close < best):
            event["best_close"] = close
            best = close
        if trigger:
            sign = 1 if bullish else -1
            event["pct_since_trigger"] = round(sign * (close / trigger - 1) * 100, 2)
            event["best_pct_since_trigger"] = round(sign * (best / trigger - 1) * 100, 2)
        if level:
            sign = 1 if bullish else -1
            event["pct_beyond_level"] = round(sign * (close / level - 1) * 100, 2)

    def _transition(self, event: dict, stage: str, bar_time: str, price: float, reason: str) -> None:
        if stage not in TERMINAL_STAGES:
            return
        event["stage"] = stage
        event["status_changed_at"] = _utc_now_iso()
        event["terminal_bar_time"] = bar_time
        event["terminal_price"] = price
        event["last_price"] = price
        event["reason"] = reason
        self.transitions.append(dict(event))

    def save(self) -> dict:
        self.state["version"] = LIFECYCLE_VERSION
        self.state["last_scan_id"] = self.scan_id
        self.state["updated_at"] = _utc_now_iso()
        self.state["events"] = self.events

        if self.redis_client:
            try:
                self.redis_client.set(
                    self.state_key,
                    json.dumps(self.state, separators=(",", ":")),
                )
            except Exception:
                pass

        snapshot = _snapshot_from_state(self.state)
        snapshot["transitions"] = list(self.transitions)
        return snapshot
