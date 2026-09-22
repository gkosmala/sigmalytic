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


def _load_state(redis_client) -> dict:
    if not redis_client:
        return {
            "version": LIFECYCLE_VERSION,
            "last_scan_id": None,
            "updated_at": None,
            "events": {},
        }
    try:
        raw = redis_client.get(WEIS_RADAR_LIFECYCLE_KEY)
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


def get_lifecycle_snapshot(redis_client) -> dict:
    """Read the currently persisted lifecycle state without running a scan."""
    return _snapshot_from_state(_load_state(redis_client))


class WeisRadarLifecycleTracker:
    """
    One tracker instance is created for each full-universe scan.

    The previous scan id lets the tracker distinguish one continuously-present
    signal from a genuinely new occurrence. A signal that stays present across
    repeated scans does not create duplicate lifecycle events. If it disappears
    for at least one completed scan and later reappears, it may open a new event.
    """

    def __init__(self, redis_client, timeframe: str, scan_id: Optional[str] = None):
        self.redis_client = redis_client
        self.timeframe = str(timeframe or "1Day")
        self.scan_id = str(scan_id or _utc_now_iso())
        self.state = _load_state(redis_client)
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
        for event in self.events.values():
            if not isinstance(event, dict):
                continue
            if event.get("symbol") != symbol or event.get("timeframe") != self.timeframe:
                continue
            if event.get("stage") != ACTIVE_STAGE:
                continue

            baseline = event.get("last_evaluated_bar_time") or event.get("trigger_bar_time")
            new_bars = [bar for bar in bars if _bar_time(bar) and _is_after(_bar_time(bar), baseline)]
            if not new_bars:
                continue

            direction = event.get("direction")
            confirmation = _float(event.get("confirmation_level"))
            invalidation = _float(event.get("invalidation_level"))
            if direction not in {"Bullish", "Bearish"} or confirmation is None or invalidation is None:
                continue

            for bar in new_bars:
                close = _float(bar.get("c"))
                bar_time = _bar_time(bar)
                if close is None:
                    continue

                event["last_price"] = close
                event["last_evaluated_bar_time"] = bar_time
                event["bars_observed_after_trigger"] = int(event.get("bars_observed_after_trigger") or 0) + 1

                if direction == "Bullish":
                    if close < invalidation:
                        self._transition(
                            event,
                            "INVALIDATED",
                            bar_time,
                            close,
                            f"Completed-bar close {close:.4f} fell below invalidation {invalidation:.4f}.",
                        )
                        break
                    if close > confirmation:
                        self._transition(
                            event,
                            "CONFIRMED",
                            bar_time,
                            close,
                            f"Completed-bar close {close:.4f} exceeded confirmation {confirmation:.4f}.",
                        )
                        break
                else:
                    if close > invalidation:
                        self._transition(
                            event,
                            "INVALIDATED",
                            bar_time,
                            close,
                            f"Completed-bar close {close:.4f} rose above invalidation {invalidation:.4f}.",
                        )
                        break
                    if close < confirmation:
                        self._transition(
                            event,
                            "CONFIRMED",
                            bar_time,
                            close,
                            f"Completed-bar close {close:.4f} fell below confirmation {confirmation:.4f}.",
                        )
                        break

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
                    WEIS_RADAR_LIFECYCLE_KEY,
                    json.dumps(self.state, separators=(",", ":")),
                )
            except Exception:
                pass

        snapshot = _snapshot_from_state(self.state)
        snapshot["transitions"] = list(self.transitions)
        return snapshot
