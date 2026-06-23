"""
SAVE AS:
backend/campaign_engine/campaign_discovery_engine.py

Sigmalytic V2
Campaign Discovery Engine with direct Alpaca fallback.

Purpose:
Discover new campaign records by:
1. Loading a production universe.
2. Fetching daily OHLCV bars.
3. Running Signal Birth.
4. Running Master Survival Index.
5. Saving qualifying BIRTH campaigns.

This version does NOT depend on /api/radar routes being wired.
It attempts:
1. SIGMALYTIC_DISCOVERY_SYMBOLS env var
2. backend.radar_service.load_russell1000()
3. Alpaca active asset universe fallback

For bars it attempts:
1. backend.radar_service.fetch_bars_batch()
2. Direct Alpaca market-data bars fallback
"""

from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from typing import Any, Callable, Dict, Iterable, List, Optional

import os
import pandas as pd
import numpy as np
import requests


try:
    from backend.research_engine.signal_birth_engine import SignalBirthEngine
except Exception:
    SignalBirthEngine = None

try:
    from backend.research_engine.master_survival_index import MasterSurvivalIndexEngine
except Exception:
    MasterSurvivalIndexEngine = None

try:
    from backend.campaign_engine.campaign_store import CampaignStore
except Exception:
    CampaignStore = None

try:
    from backend.radar_service import load_russell1000, fetch_bars_batch
except Exception:
    load_russell1000 = None
    fetch_bars_batch = None


@dataclass
class CampaignDiscoveryVerdict:
    symbol: str
    timeframe: str
    discovered: bool
    reason: str
    birth_score: float
    birth_state: str
    birth_eligible: bool
    master_campaign_index: float
    master_verdict: str
    campaign_quality: str
    master_survival_score: float
    survival_state: str
    survival_grade: str
    survival_confirmed: bool
    current_state: str
    payload: Dict[str, Any]
    birth_details: Dict[str, Any]
    survival_details: Dict[str, Any]
    as_of: str

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


class CampaignDiscoveryEngine:
    def __init__(
        self,
        store: Optional[Any] = None,
        data_loader: Optional[Callable[[str, str], Optional[pd.DataFrame]]] = None,
        sister_loader: Optional[Callable[[str, str], Optional[pd.DataFrame]]] = None,
        birth_threshold: Optional[float] = None,
        survival_threshold: Optional[float] = None,
        mci_threshold: Optional[float] = None,
        timeframe: str = "DAILY",
        max_symbols: Optional[int] = None,
        bar_limit: Optional[int] = None,
    ):
        self.store = store or (CampaignStore() if CampaignStore is not None else None)
        self.data_loader = data_loader
        self.sister_loader = sister_loader

        self.birth_threshold = float(
            birth_threshold if birth_threshold is not None
            else os.getenv("CAMPAIGN_DISCOVERY_BIRTH_THRESHOLD", "55")
        )
        self.survival_threshold = float(
            survival_threshold if survival_threshold is not None
            else os.getenv("CAMPAIGN_DISCOVERY_SURVIVAL_THRESHOLD", "50")
        )
        self.mci_threshold = float(
            mci_threshold if mci_threshold is not None
            else os.getenv("CAMPAIGN_DISCOVERY_MCI_THRESHOLD", "25")
        )

        self.timeframe = timeframe.upper()
        self.max_symbols = int(max_symbols or os.getenv("CAMPAIGN_DISCOVERY_MAX_SYMBOLS", "1500"))
        self.bar_limit = int(bar_limit or os.getenv("CAMPAIGN_DISCOVERY_BAR_LIMIT", "252"))

        self.birth_engine = SignalBirthEngine() if SignalBirthEngine is not None else None
        self.survival_engine = MasterSurvivalIndexEngine() if MasterSurvivalIndexEngine is not None else None
        self.diagnostics: Dict[str, Any] = {}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None:
                return default
            return round(float(value), 2)
        except Exception:
            return default

    @staticmethod
    def _headers() -> Dict[str, str]:
        key = (
            os.getenv("ALPACA_API_KEY")
            or os.getenv("APCA_API_KEY_ID")
        )

        secret = (
            os.getenv("ALPACA_API_SECRET")
            or os.getenv("ALPACA_SECRET_KEY")
            or os.getenv("APCA_API_SECRET_KEY")
        )

        if not key or not secret:
            return {}

        return {
            "APCA-API-KEY-ID": key,
            "APCA-API-SECRET-KEY": secret,
        }

    @staticmethod
    def _alpaca_trading_base_url() -> str:
        paper = str(os.getenv("ALPACA_PAPER", "false")).lower() in {"1", "true", "yes", "y"}
        return "https://paper-api.alpaca.markets" if paper else "https://api.alpaca.markets"

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (np.integer,)):
            return int(value)
        if isinstance(value, (np.floating,)):
            return float(value)
        if isinstance(value, (np.bool_,)):
            return bool(value)
        if isinstance(value, pd.Timestamp):
            return value.isoformat()
        if isinstance(value, dict):
            return {str(k): CampaignDiscoveryEngine._json_safe(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [CampaignDiscoveryEngine._json_safe(v) for v in value]
        if hasattr(value, "item"):
            try:
                return value.item()
            except Exception:
                return str(value)
        return value

    def _debug_dataframe_snapshot(self, symbol: str, df: Optional[pd.DataFrame]) -> Dict[str, Any]:
        if str(os.getenv("CAMPAIGN_DISCOVERY_DEBUG", "false")).lower() not in {"1", "true", "yes", "y"}:
            return {}

        debug_symbols = {
            s.strip().upper()
            for s in os.getenv(
                "CAMPAIGN_DISCOVERY_DEBUG_SYMBOLS",
                "NVDA,PLTR,MSTR,META,SMCI",
            ).split(",")
            if s.strip()
        }

        symbol = str(symbol or "").upper().strip()

        if symbol not in debug_symbols:
            return {}

        if df is None or df.empty:
            snapshot = {"symbol": symbol, "error": "Dataframe is None or empty", "row_count": 0}
            print(f"📢 [DEBUG SNAPSHOT] {symbol} | EMPTY DATAFRAME")
            return snapshot

        col_map = {str(c).lower(): c for c in df.columns}
        close_col = col_map.get("close") or col_map.get("c")

        def sanitize(value: Any) -> Any:
            return CampaignDiscoveryEngine._json_safe(value)

        def sanitize_row(row: Dict[str, Any]) -> Dict[str, Any]:
            return {str(k): sanitize(v) for k, v in row.items()}

        first_close = None
        last_close = None
        if close_col in df.columns:
            try:
                first_close = float(df[close_col].iloc[0])
            except Exception:
                first_close = None
            try:
                last_close = float(df[close_col].iloc[-1])
            except Exception:
                last_close = None

        snapshot = {
            "symbol": symbol,
            "row_count": int(len(df)),
            "columns": [str(c) for c in df.columns],
            "index_type": str(type(df.index).__name__),
            "first_index": str(df.index[0]),
            "last_index": str(df.index[-1]),
            "first_close": first_close,
            "last_close": last_close,
            "null_counts": {str(k): int(v) for k, v in df.isnull().sum().to_dict().items()},
            "head": [sanitize_row(r) for r in df.head(3).to_dict("records")],
            "tail": [sanitize_row(r) for r in df.tail(3).to_dict("records")],
        }

        print(
            f"📢 [DEBUG SNAPSHOT] {symbol} | "
            f"Rows={snapshot['row_count']} | "
            f"Order={snapshot['first_index']} -> {snapshot['last_index']} | "
            f"Close={snapshot['first_close']} -> {snapshot['last_close']} | "
            f"Columns={snapshot['columns']}"
        )

        return snapshot

    @staticmethod
    def _normalize_symbol(symbol: Any) -> str:
        return str(symbol or "").upper().strip()

    @staticmethod
    def _clean_universe(symbols: Iterable[Any], limit: int) -> List[str]:
        out: List[str] = []
        seen = set()
        for raw in symbols or []:
            sym = CampaignDiscoveryEngine._normalize_symbol(raw)
            if not sym:
                continue
            if "." in sym or "/" in sym or "-" in sym:
                continue
            if len(sym) > 6:
                continue
            if sym in seen:
                continue
            seen.add(sym)
            out.append(sym)
            if limit and len(out) >= limit:
                break
        return out

    @staticmethod
    def _normalize_bar_row(row: Dict[str, Any]) -> Dict[str, Any]:
        normalized = {
            "open": row.get("open", row.get("o")),
            "high": row.get("high", row.get("h")),
            "low": row.get("low", row.get("l")),
            "close": row.get("close", row.get("c")),
            "volume": row.get("volume", row.get("v")),
        }
        ts = row.get("timestamp") or row.get("time") or row.get("date") or row.get("t")
        if ts is not None:
            normalized["timestamp"] = ts
        return normalized

    @classmethod
    def _normalize_bars(cls, raw_bars: Any) -> Optional[List[Dict[str, Any]]]:
        if raw_bars is None:
            return None

        if isinstance(raw_bars, pd.DataFrame):
            if raw_bars.empty:
                return None
            rows = raw_bars.reset_index(drop=True).to_dict("records")
            return [cls._normalize_bar_row(r) for r in rows]

        if isinstance(raw_bars, dict):
            if "bars" in raw_bars:
                return cls._normalize_bars(raw_bars.get("bars"))
            return None

        if isinstance(raw_bars, list):
            rows = [cls._normalize_bar_row(r) for r in raw_bars if isinstance(r, dict)]
            rows = [
                r for r in rows
                if all(r.get(k) is not None for k in ("open", "high", "low", "close", "volume"))
            ]
            return rows or None

        return None

    def _load_alpaca_assets(self) -> List[str]:
        headers = self._headers()
        if not headers:
            self.diagnostics["alpaca_assets_error"] = "Missing Alpaca credentials."
            return []

        try:
            response = requests.get(
                f"{self._alpaca_trading_base_url()}/v2/assets",
                headers=headers,
                params={"status": "active", "asset_class": "us_equity"},
                timeout=25,
            )
            response.raise_for_status()
            assets = response.json() or []
            symbols = [
                row.get("symbol")
                for row in assets
                if row.get("tradable") is True
            ]
            return self._clean_universe(symbols, self.max_symbols)
        except Exception as exc:
            self.diagnostics["alpaca_assets_error"] = str(exc)
            return []

    def load_universe_symbols(self, symbols: Optional[Iterable[str]] = None) -> List[str]:
        if symbols:
            cleaned = self._clean_universe(symbols, self.max_symbols)
            self.diagnostics["universe_source"] = "provided_symbols"
            self.diagnostics["universe_count"] = len(cleaned)
            return cleaned

        env_symbols = os.getenv("SIGMALYTIC_DISCOVERY_SYMBOLS", "")
        if env_symbols:
            cleaned = self._clean_universe(env_symbols.split(","), self.max_symbols)
            self.diagnostics["universe_source"] = "SIGMALYTIC_DISCOVERY_SYMBOLS"
            self.diagnostics["universe_count"] = len(cleaned)
            return cleaned

        if load_russell1000 is not None:
            try:
                loaded = load_russell1000()
                cleaned = self._clean_universe(loaded, self.max_symbols)
                if cleaned:
                    self.diagnostics["universe_source"] = "radar_service.load_russell1000"
                    self.diagnostics["universe_count"] = len(cleaned)
                    return cleaned
            except Exception as exc:
                self.diagnostics["radar_universe_error"] = str(exc)

        cleaned = self._load_alpaca_assets()
        self.diagnostics["universe_source"] = "alpaca_assets_fallback"
        self.diagnostics["universe_count"] = len(cleaned)
        return cleaned

    def _fetch_bars_from_radar(self, universe: List[str]) -> Dict[str, Any]:
        if fetch_bars_batch is None:
            self.diagnostics["radar_bars_error"] = "fetch_bars_batch unavailable."
            return {}

        try:
            bars_cache = fetch_bars_batch(universe, timeframe="1Day", limit=self.bar_limit)
            if isinstance(bars_cache, dict):
                self.diagnostics["radar_bars_symbols"] = len(bars_cache)
                return bars_cache
            return {}
        except Exception as exc:
            self.diagnostics["radar_bars_error"] = str(exc)
            return {}

    def _fetch_bars_from_alpaca(self, universe: List[str]) -> Dict[str, Any]:
        """
        Fetch historical daily bars from Alpaca.

        This fixes the incomplete universe coverage seen when pagination stopped
        at 20 pages with too small a per-page limit.

        Separate controls:
            CAMPAIGN_DISCOVERY_BAR_LIMIT = bars kept per symbol, default 252
            CAMPAIGN_DISCOVERY_ALPACA_PAGE_LIMIT = rows requested per API page, default 10000
            CAMPAIGN_DISCOVERY_BAR_BATCH = symbols per API batch, default 50
            CAMPAIGN_DISCOVERY_MAX_BAR_PAGES = safety cap per batch, default 200
        """
        headers = self._headers()
        if not headers:
            self.diagnostics["alpaca_bars_error"] = "Missing Alpaca credentials."
            return {}

        base_url = os.getenv("ALPACA_DATA_BASE_URL", "https://data.alpaca.markets")
        feed = os.getenv("ALPACA_FEED", "sip")
        batch_size = int(os.getenv("CAMPAIGN_DISCOVERY_BAR_BATCH", "50"))
        page_limit = int(os.getenv("CAMPAIGN_DISCOVERY_ALPACA_PAGE_LIMIT", "10000"))
        max_pages = int(os.getenv("CAMPAIGN_DISCOVERY_MAX_BAR_PAGES", "200"))

        calendar_days = int(os.getenv(
            "CAMPAIGN_DISCOVERY_LOOKBACK_CALENDAR_DAYS",
            str(max(390, self.bar_limit * 3)),
        ))

        end_dt = datetime.now(timezone.utc)
        start_dt = end_dt - timedelta(days=calendar_days)

        results: Dict[str, List[Dict[str, Any]]] = {}

        self.diagnostics["alpaca_bar_limit_requested"] = int(self.bar_limit)
        self.diagnostics["alpaca_page_limit_requested"] = int(page_limit)
        self.diagnostics["alpaca_batch_size"] = int(batch_size)
        self.diagnostics["alpaca_max_pages_per_batch"] = int(max_pages)
        self.diagnostics["alpaca_lookback_calendar_days"] = int(calendar_days)
        self.diagnostics["alpaca_feed"] = str(feed)

        batches_attempted = 0
        total_pages_loaded = 0

        for start_idx in range(0, len(universe), batch_size):
            batch = universe[start_idx:start_idx + batch_size]
            batches_attempted += 1
            page_token = None
            page_count = 0

            while True:
                params = {
                    "symbols": ",".join(batch),
                    "timeframe": "1Day",
                    "limit": page_limit,
                    "feed": feed,
                    "adjustment": "raw",
                    "start": start_dt.isoformat().replace("+00:00", "Z"),
                    "end": end_dt.isoformat().replace("+00:00", "Z"),
                }

                if page_token:
                    params["page_token"] = page_token

                try:
                    response = requests.get(
                        f"{base_url}/v2/stocks/bars",
                        headers=headers,
                        params=params,
                        timeout=60,
                    )
                    response.raise_for_status()
                    data = response.json() or {}
                    bars = data.get("bars") or {}

                    if isinstance(bars, dict):
                        for sym, rows in bars.items():
                            normalized = self._normalize_bars(rows)
                            if normalized:
                                key = sym.upper()
                                results.setdefault(key, [])
                                results[key].extend(normalized)

                    page_token = data.get("next_page_token")
                    page_count += 1
                    total_pages_loaded += 1

                    if not page_token:
                        break

                    if page_count >= max_pages:
                        self.diagnostics.setdefault("alpaca_pagination_warnings", []).append(
                            f"Stopped pagination after {page_count} pages for batch starting {batch[0]}"
                        )
                        break

                except Exception as exc:
                    self.diagnostics.setdefault("alpaca_bars_errors", []).append(
                        f"batch_start={batch[0]} error={str(exc)[:220]}"
                    )
                    break

        cleaned: Dict[str, List[Dict[str, Any]]] = {}

        for sym, rows in results.items():
            if not rows:
                continue

            dedup: Dict[str, Dict[str, Any]] = {}
            no_ts_rows: List[Dict[str, Any]] = []

            for row in rows:
                ts = row.get("timestamp")
                if ts is not None:
                    dedup[str(ts)] = row
                else:
                    no_ts_rows.append(row)

            final_rows = list(dedup.values()) if dedup else no_ts_rows

            if final_rows and "timestamp" in final_rows[0]:
                final_rows = sorted(final_rows, key=lambda r: str(r.get("timestamp")))

            final_rows = final_rows[-self.bar_limit:]

            if final_rows:
                cleaned[sym.upper()] = final_rows

        self.diagnostics["alpaca_batches_attempted"] = int(batches_attempted)
        self.diagnostics["alpaca_total_pages_loaded"] = int(total_pages_loaded)

        if cleaned:
            lengths = [len(v) for v in cleaned.values()]
            self.diagnostics["alpaca_bars_symbols"] = len(cleaned)
            self.diagnostics["alpaca_min_bars_per_symbol"] = int(min(lengths))
            self.diagnostics["alpaca_max_bars_per_symbol"] = int(max(lengths))
            self.diagnostics["alpaca_avg_bars_per_symbol"] = round(float(sum(lengths) / len(lengths)), 2)

            min_usable = int(os.getenv("CAMPAIGN_DISCOVERY_MIN_USABLE_BARS", "120"))
            usable = [length for length in lengths if length >= min_usable]
            self.diagnostics["alpaca_symbols_with_120plus_bars"] = int(len(usable))
        else:
            self.diagnostics["alpaca_bars_symbols"] = 0
            self.diagnostics["alpaca_symbols_with_120plus_bars"] = 0

        return cleaned

    def build_records_from_universe(self, symbols: Optional[Iterable[str]] = None) -> List[Dict[str, Any]]:
        self.diagnostics = {}
        universe = self.load_universe_symbols(symbols=symbols)
        if not universe:
            return []

        bars_cache = self._fetch_bars_from_radar(universe)
        if not bars_cache:
            bars_cache = self._fetch_bars_from_alpaca(universe)

        records: List[Dict[str, Any]] = []

        for symbol in universe:
            raw = None
            if isinstance(bars_cache, dict):
                raw = bars_cache.get(symbol) or bars_cache.get(symbol.upper())

            bars = self._normalize_bars(raw)
            if not bars:
                continue

            records.append(
                {
                    "symbol": symbol.upper(),
                    "timeframe": self.timeframe,
                    "bars": bars,
                }
            )

        self.diagnostics["records_built"] = len(records)
        if records:
            lengths = [len(r.get("bars", [])) for r in records]
            self.diagnostics["record_min_bars"] = int(min(lengths))
            self.diagnostics["record_max_bars"] = int(max(lengths))
            self.diagnostics["record_avg_bars"] = round(float(sum(lengths) / len(lengths)), 2)
        return records

    def _bars_from_record(self, record: Dict[str, Any]) -> Optional[pd.DataFrame]:
        bars = self._normalize_bars(record.get("bars"))
        if not bars:
            return None

        df = pd.DataFrame(bars)
        required = {"open", "high", "low", "close", "volume"}
        if not required.issubset(df.columns):
            return None

        if "timestamp" in df.columns:
            df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce", utc=True)
            df = df.sort_values("timestamp", ascending=True).reset_index(drop=True)
        else:
            df = df.reset_index(drop=True)

        for col in ["open", "high", "low", "close", "volume"]:
            df[col] = pd.to_numeric(df[col], errors="coerce")

        df = df.dropna(subset=["open", "high", "low", "close", "volume"]).reset_index(drop=True)

        if len(df) == 0:
            return None

        return df

    def _sister_bars_from_record(self, record: Dict[str, Any]) -> Optional[pd.DataFrame]:
        bars = self._normalize_bars(record.get("sister_bars") or record.get("sector_bars"))
        if not bars:
            return None
        return pd.DataFrame(bars)

    def _load_bars(self, symbol: str, timeframe: str, record: Optional[Dict[str, Any]] = None) -> Optional[pd.DataFrame]:
        if record:
            df = self._bars_from_record(record)
            if df is not None:
                return df
        if self.data_loader is None:
            return None
        return self.data_loader(symbol, timeframe)

    def _load_sister_bars(self, symbol: str, timeframe: str, record: Optional[Dict[str, Any]] = None) -> Optional[pd.DataFrame]:
        if record:
            df = self._sister_bars_from_record(record)
            if df is not None:
                return df
        if self.sister_loader is None:
            return None
        return self.sister_loader(symbol, timeframe)

    def _build_campaign_payload(self, symbol: str, timeframe: str, birth: Dict[str, Any], survival: Dict[str, Any], current_close: Optional[float]) -> Dict[str, Any]:
        now = self._now()

        return {
            "symbol": symbol.upper(),
            "timeframe": timeframe.upper(),
            "display_label": f"{symbol.upper()} {timeframe.upper()} Campaign",
            "birth_date": now[:10],
            "campaign_age_days": 0,
            "current_state": "BIRTH",
            "state_enum": "BIRTH",
            "current_price": current_close,
            "entry_price": current_close,
            "status": "active",
            "layer": "DISCOVERY",
            "operator_dominance": self._safe_float(birth.get("master_campaign_index")),
            "obstacle_score": self._safe_float(birth.get("resistance_score")),
            "progress_score": self._safe_float(birth.get("behavioral_resolution_score")),
            "d_score": self._safe_float(survival.get("master_survival_score")),
            "historical_confidence": str(birth.get("campaign_quality", "UNKNOWN")),
            "close_notes": (
                f"Discovery created by campaign_discovery_engine; "
                f"birth={self._safe_float(birth.get('birth_score'))}, "
                f"mci={self._safe_float(birth.get('master_campaign_index'))}, "
                f"survival={self._safe_float(survival.get('master_survival_score'))}"
            ),
            "created_at": now,
            "updated_at": now,
            "state_changed_at": now,
        }

    def _empty_verdict(self, symbol: str, timeframe: str, reason: str, state: str = "NO_BARS") -> Dict[str, Any]:
        return CampaignDiscoveryVerdict(
            symbol=symbol,
            timeframe=timeframe,
            discovered=False,
            reason=reason,
            birth_score=0.0,
            birth_state=state,
            birth_eligible=False,
            master_campaign_index=0.0,
            master_verdict=state,
            campaign_quality="F",
            master_survival_score=0.0,
            survival_state=state,
            survival_grade="F",
            survival_confirmed=False,
            current_state="NO_CAMPAIGN",
            payload={},
            birth_details={},
            survival_details={},
            as_of=self._now(),
        ).to_dict()

    def evaluate_record(self, record: Dict[str, Any]) -> Dict[str, Any]:
        symbol = str(record.get("symbol", "")).upper().strip()
        timeframe = str(record.get("timeframe") or self.timeframe).upper().strip()

        if not symbol:
            return self._empty_verdict("", timeframe, "Missing symbol.", "NO_SYMBOL")

        df = self._load_bars(symbol, timeframe, record=record)
        sister_df = self._load_sister_bars(symbol, timeframe, record=record)
        debug_snapshot = self._debug_dataframe_snapshot(symbol, df)

        if df is None or len(df) == 0:
            verdict = self._empty_verdict(symbol, timeframe, "No OHLCV bars supplied or loaded.", "NO_BARS")
            if debug_snapshot:
                verdict["debug_snapshot"] = debug_snapshot
            return self._json_safe(verdict)

        if self.birth_engine is None:
            raise RuntimeError("SignalBirthEngine unavailable.")

        birth = self.birth_engine.evaluate_bars(df, sister_df=sister_df, symbol=symbol)

        if self.survival_engine is not None:
            survival = self.survival_engine.evaluate_bars(df, symbol=symbol, sister_df=sister_df)
        else:
            survival = {
                "master_survival_score": 0.0,
                "survival_state": "MASTER_SURVIVAL_INDEX_UNAVAILABLE",
                "survival_grade": "F",
                "survival_confirmed": False,
            }

        birth_score = self._safe_float(birth.get("birth_score"))
        mci = self._safe_float(birth.get("master_campaign_index"))
        survival_score = self._safe_float(survival.get("master_survival_score"))

        try:
            current_close = round(float(df["close"].iloc[-1]), 4)
        except Exception:
            current_close = None

        discovered = birth_score >= self.birth_threshold and mci >= self.mci_threshold and survival_score >= self.survival_threshold
        reason = (
            f"Discovery {'accepted' if discovered else 'rejected'}; "
            f"birth={birth_score}, mci={mci}, survival={survival_score}; "
            f"thresholds birth>={self.birth_threshold}, mci>={self.mci_threshold}, survival>={self.survival_threshold}."
        )

        payload: Dict[str, Any] = {}
        if discovered:
            payload = self._build_campaign_payload(symbol, timeframe, birth, survival, current_close)
            if self.store is not None and getattr(self.store, "configured", lambda: False)():
                self.store.save_campaign(payload)

        verdict = CampaignDiscoveryVerdict(
            symbol=symbol,
            timeframe=timeframe,
            discovered=discovered,
            reason=reason,
            birth_score=birth_score,
            birth_state=str(birth.get("birth_state", "UNKNOWN")),
            birth_eligible=bool(birth.get("birth_eligible", False)),
            master_campaign_index=mci,
            master_verdict=str(birth.get("master_verdict", "UNKNOWN")),
            campaign_quality=str(birth.get("campaign_quality", "F")),
            master_survival_score=survival_score,
            survival_state=str(survival.get("survival_state", "UNKNOWN")),
            survival_grade=str(survival.get("survival_grade", "F")),
            survival_confirmed=bool(survival.get("survival_confirmed", False)),
            current_state="BIRTH" if discovered else "NO_CAMPAIGN",
            payload=payload,
            birth_details=birth,
            survival_details=survival,
            as_of=self._now(),
        ).to_dict()

        if debug_snapshot:
            verdict["debug_snapshot"] = debug_snapshot

        return self._json_safe(verdict)

    def run_records(self, records: List[Dict[str, Any]]) -> Dict[str, Any]:
        results = [self.evaluate_record(record) for record in records]
        discovered = [row for row in results if row.get("discovered")]
        return self._json_safe({
            "ok": True,
            "engine": "campaign_discovery_engine",
            "records_evaluated": len(results),
            "campaigns_discovered": len(discovered),
            "discovered_symbols": [row.get("symbol") for row in discovered],
            "results": results[:100],
            "diagnostics": self.diagnostics,
            "as_of": self._now(),
        })

    def run_symbols(self, symbols: Iterable[str], timeframe: Optional[str] = None) -> Dict[str, Any]:
        records = self.build_records_from_universe(symbols=symbols)
        return self.run_records(records)

    def run(self, records: Optional[List[Dict[str, Any]]] = None, symbols: Optional[Iterable[str]] = None, timeframe: Optional[str] = None) -> Dict[str, Any]:
        if records:
            return self.run_records(records)

        records = self.build_records_from_universe(symbols=symbols)

        if records:
            return self.run_records(records)

        return self._json_safe({
            "ok": True,
            "engine": "campaign_discovery_engine",
            "records_evaluated": 0,
            "campaigns_discovered": 0,
            "discovered_symbols": [],
            "results": [],
            "diagnostics": self.diagnostics,
            "message": "No universe symbols or OHLCV bars available.",
            "as_of": self._now(),
        })


def run_campaign_discovery(records: Optional[List[Dict[str, Any]]] = None, symbols: Optional[Iterable[str]] = None, timeframe: str = "DAILY") -> Dict[str, Any]:
    return CampaignDiscoveryEngine(timeframe=timeframe).run(records=records, symbols=symbols, timeframe=timeframe)


CampaignDiscoveryRunner = CampaignDiscoveryEngine


__all__ = [
    "CampaignDiscoveryEngine",
    "CampaignDiscoveryVerdict",
    "CampaignDiscoveryRunner",
    "run_campaign_discovery",
]
