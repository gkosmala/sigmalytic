from __future__ import annotations

"""
Sigmalytic V2
Alpaca Option Chain Adapter

Purpose:
- Fetch Alpaca option-chain snapshots.
- Normalize option-chain rows into the internal Weis-Gamma format.
- Never controls campaign lifecycle transitions directly.

Internal normalized row shape:
{
    "contract_symbol": str,
    "underlying_symbol": str,
    "strike": float,
    "option_type": "CALL" | "PUT",
    "expiration_date": str | None,
    "dte": int | None,
    "open_interest": float,
    "volume": float,
    "gamma": float,
    "delta": float,
    "theta": float,
    "vega": float,
    "implied_volatility": float | None,
    "gamma_exposure": float,
    "net_delta_shares": float,
    "bid": float | None,
    "ask": float | None,
    "last": float | None,
    "snapshot_time": str | None,
}
"""

import math
import os
import re
from datetime import date, datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests


CONTRACT_MULTIPLIER = 100.0


class AlpacaOptionChainAdapter:
    DEFAULT_BASE_URL = "https://data.alpaca.markets"
    # DEFAULT_FEED intentionally removed (2026-07-30) -- see fetch_chain's
    # feed-parameter handling for why.

    @classmethod
    def _api_key(cls) -> str:
        return (
            os.getenv("ALPACA_API_KEY")
            or os.getenv("ALPACA_KEY_ID")
            or os.getenv("APCA_API_KEY_ID")
            or ""
        )

    @classmethod
    def _api_secret(cls) -> str:
        return (
            os.getenv("ALPACA_API_SECRET")
            or os.getenv("ALPACA_SECRET_KEY")
            or os.getenv("APCA_API_SECRET_KEY")
            or ""
        )

    @classmethod
    def _headers(cls) -> Dict[str, str]:
        return {
            "APCA-API-KEY-ID": cls._api_key(),
            "APCA-API-SECRET-KEY": cls._api_secret(),
        }

    @staticmethod
    def _safe_float(value: Any, default: float = 0.0) -> float:
        try:
            if value is None or value == "":
                return default
            out = float(value)
            if math.isnan(out) or math.isinf(out):
                return default
            return out
        except Exception:
            return default

    @staticmethod
    def _safe_optional_float(value: Any) -> Optional[float]:
        try:
            if value is None or value == "":
                return None
            out = float(value)
            if math.isnan(out) or math.isinf(out):
                return None
            return out
        except Exception:
            return None

    @staticmethod
    def _parse_contract(symbol: str) -> Dict[str, Any]:
        """
        Parses OCC-style symbols such as AAPL240119C00190000.

        Returns best-effort fields only. Alpaca payload fields override this
        when available.
        """
        raw = str(symbol or "").upper().strip()

        match = re.match(
            r"^(?P<root>[A-Z]{1,6})(?P<yy>\d{2})(?P<mm>\d{2})(?P<dd>\d{2})(?P<type>[CP])(?P<strike>\d{8})$",
            raw,
        )

        if not match:
            return {
                "underlying_symbol": None,
                "expiration_date": None,
                "option_type": None,
                "strike": None,
                "dte": None,
            }

        gd = match.groupdict()

        expiration_date = None
        dte = None

        try:
            year = 2000 + int(gd["yy"])
            month = int(gd["mm"])
            day = int(gd["dd"])
            exp = date(year, month, day)
            expiration_date = exp.isoformat()
            dte = max((exp - datetime.now(timezone.utc).date()).days, 0)
        except Exception:
            pass

        strike = None
        try:
            strike = int(gd["strike"]) / 1000.0
        except Exception:
            pass

        return {
            "underlying_symbol": gd["root"],
            "expiration_date": expiration_date,
            "option_type": "CALL" if gd["type"] == "C" else "PUT",
            "strike": strike,
            "dte": dte,
        }

    @classmethod
    def _nested_get(cls, obj: Dict[str, Any], *keys: str) -> Any:
        cur: Any = obj
        for key in keys:
            if not isinstance(cur, dict):
                return None
            cur = cur.get(key)
        return cur

    @classmethod
    def normalize_snapshot(
        cls,
        contract_symbol: str,
        snapshot: Dict[str, Any],
        underlying_symbol: str,
        spot_price: Optional[float] = None,
    ) -> Dict[str, Any]:
        parsed = cls._parse_contract(contract_symbol)

        contract = snapshot.get("contract") or snapshot.get("details") or {}

        strike = (
            cls._safe_optional_float(contract.get("strike_price"))
            or cls._safe_optional_float(contract.get("strike"))
            or parsed.get("strike")
        )

        option_type = (
            contract.get("type")
            or contract.get("option_type")
            or parsed.get("option_type")
            or ""
        )
        option_type = str(option_type).upper()

        if option_type == "CALL":
            sign = 1.0
        elif option_type == "PUT":
            sign = -1.0
        else:
            sign = 0.0

        expiration_date = (
            contract.get("expiration_date")
            or contract.get("expiration")
            or parsed.get("expiration_date")
        )

        dte = parsed.get("dte")
        if expiration_date:
            try:
                exp = datetime.fromisoformat(str(expiration_date)).date()
                dte = max((exp - datetime.now(timezone.utc).date()).days, 0)
            except Exception:
                pass

        greeks = snapshot.get("greeks") or {}
        latest_trade = snapshot.get("latest_trade") or snapshot.get("trade") or {}
        latest_quote = snapshot.get("latest_quote") or snapshot.get("quote") or {}

        # FIX (2026-07-30): confirmed via direct inspection of Alpaca's
        # actual raw response that this endpoint uses camelCase keys with
        # abbreviated sub-fields (dailyBar.v, latestTrade.s), not the
        # snake_case/spelled-out names this was checking for -- volume
        # was silently defaulting to 0.0 for every single contract.
        volume = (
            cls._safe_float(snapshot.get("volume"), 0.0)
            or cls._safe_float(cls._nested_get(snapshot, "dailyBar", "v"), 0.0)
            or cls._safe_float(cls._nested_get(snapshot, "daily_bar", "volume"), 0.0)
            or cls._safe_float(cls._nested_get(snapshot, "latestTrade", "s"), 0.0)
            or cls._safe_float(cls._nested_get(snapshot, "latest_trade", "size"), 0.0)
        )

        open_interest = (
            cls._safe_float(snapshot.get("open_interest"), 0.0)
            or cls._safe_float(snapshot.get("openInterest"), 0.0)
            or cls._safe_float(contract.get("open_interest"), 0.0)
            or cls._safe_float(contract.get("openInterest"), 0.0)
        )

        gamma = cls._safe_float(greeks.get("gamma"), 0.0)
        delta = cls._safe_float(greeks.get("delta"), 0.0)
        theta = cls._safe_float(greeks.get("theta"), 0.0)
        vega = cls._safe_float(greeks.get("vega"), 0.0)
        iv = cls._safe_optional_float(
            greeks.get("implied_volatility")
            or greeks.get("iv")
            or snapshot.get("implied_volatility")
        )

        gamma_exposure = gamma * open_interest * CONTRACT_MULTIPLIER
        if spot_price:
            gamma_exposure = gamma_exposure * float(spot_price)

        gamma_exposure = gamma_exposure * sign
        net_delta_shares = delta * open_interest * CONTRACT_MULTIPLIER

        bid = cls._safe_optional_float(
            latest_quote.get("bid_price") or latest_quote.get("bp")
        )
        ask = cls._safe_optional_float(
            latest_quote.get("ask_price") or latest_quote.get("ap")
        )
        last = cls._safe_optional_float(
            latest_trade.get("price") or latest_trade.get("p")
        )

        snapshot_time = (
            latest_trade.get("timestamp")
            or latest_trade.get("t")
            or latest_quote.get("timestamp")
            or latest_quote.get("t")
            or snapshot.get("updated_at")
            or snapshot.get("timestamp")
        )

        return {
            "contract_symbol": str(contract_symbol or "").upper(),
            "underlying_symbol": str(underlying_symbol or parsed.get("underlying_symbol") or "").upper(),
            "strike": float(strike or 0.0),
            "option_type": option_type,
            "expiration_date": expiration_date,
            "dte": dte,
            "open_interest": open_interest,
            "volume": volume,
            "gamma": gamma,
            "delta": delta,
            "theta": theta,
            "vega": vega,
            "implied_volatility": iv,
            "gamma_exposure": gamma_exposure,
            "net_delta_shares": net_delta_shares,
            "bid": bid,
            "ask": ask,
            "last": last,
            "snapshot_time": snapshot_time,
        }

    @classmethod
    def normalize_chain(
        cls,
        payload: Any,
        underlying_symbol: str,
        spot_price: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        if not payload:
            return []

        snapshots: Any = payload

        if isinstance(payload, dict):
            snapshots = (
                payload.get("snapshots")
                or payload.get("options")
                or payload.get("data")
                or payload.get("results")
                or payload
            )

        rows: List[Dict[str, Any]] = []

        if isinstance(snapshots, dict):
            iterator = snapshots.items()
        elif isinstance(snapshots, list):
            iterator = []
            for item in snapshots:
                if not isinstance(item, dict):
                    continue
                symbol = (
                    item.get("symbol")
                    or item.get("contract_symbol")
                    or item.get("contractSymbol")
                    or item.get("option_symbol")
                    or item.get("optionSymbol")
                )
                iterator.append((symbol, item))
        else:
            return []

        for contract_symbol, snapshot in iterator:
            if not contract_symbol or not isinstance(snapshot, dict):
                continue

            row = cls.normalize_snapshot(
                contract_symbol=str(contract_symbol),
                snapshot=snapshot,
                underlying_symbol=underlying_symbol,
                spot_price=spot_price,
            )

            if row["strike"] <= 0 or row["option_type"] not in {"CALL", "PUT"}:
                continue

            rows.append(row)

        return rows

    @classmethod
    def fetch_chain(
        cls,
        symbol: str,
        spot_price: Optional[float] = None,
        feed: Optional[str] = None,
        limit: int = 1000,
        max_pages: int = 3,
        strike_price_gte: Optional[float] = None,
        strike_price_lte: Optional[float] = None,
        expiration_date_gte: Optional[str] = None,
        expiration_date_lte: Optional[str] = None,
        timeout: int = 8,
    ) -> Dict[str, Any]:
        symbol = str(symbol or "").upper().strip()

        if not symbol:
            return {
                "status": "NO_SYMBOL",
                "symbol": symbol,
                "options_data": [],
                "source": "alpaca_option_chain",
            }

        if not cls._api_key() or not cls._api_secret():
            return {
                "status": "MISSING_ALPACA_CREDENTIALS",
                "symbol": symbol,
                "options_data": [],
                "source": "alpaca_option_chain",
            }

        base_url = os.getenv("ALPACA_BASE_URL", cls.DEFAULT_BASE_URL).rstrip("/")
        chain_url = f"{base_url}/v1beta1/options/snapshots/{symbol}"

        # FIX (2026-07-30): confirmed directly against Alpaca's own docs
        # (docs.alpaca.markets/reference/optionchain) that this feed
        # parameter defaults to "opra" (the official, full feed) on
        # Alpaca's own side automatically -- IF the account has an OPRA
        # subscription -- and only falls back to "indicative" (a
        # limited, delayed feed) if it doesn't. This code was
        # unconditionally hardcoding "indicative" as our own default,
        # meaning we were forcing the limited feed even for an account
        # that might actually be entitled to full data, rather than
        # letting Alpaca apply its own real entitlement-aware default.
        # Confirmed via a raw response dump that greeks were completely
        # absent under indicative -- omitting the parameter entirely
        # unless explicitly overridden lets Alpaca decide correctly.
        _resolved_feed = feed or os.getenv("ALPACA_OPTIONS_FEED")

        params: Dict[str, Any] = {
            "limit": int(limit),
        }
        if _resolved_feed:
            params["feed"] = _resolved_feed

        if strike_price_gte is not None:
            params["strike_price_gte"] = float(strike_price_gte)
        if strike_price_lte is not None:
            params["strike_price_lte"] = float(strike_price_lte)
        if expiration_date_gte:
            params["expiration_date_gte"] = expiration_date_gte
        if expiration_date_lte:
            params["expiration_date_lte"] = expiration_date_lte

        all_rows: List[Dict[str, Any]] = []
        page_token: Optional[str] = None
        pages = 0
        errors: List[str] = []

        while pages < max_pages:
            req_params = dict(params)
            if page_token:
                req_params["page_token"] = page_token

            try:
                response = requests.get(
                    chain_url,
                    headers=cls._headers(),
                    params=req_params,
                    timeout=timeout,
                )

                if not response.ok:
                    return {
                        "status": "HTTP_ERROR",
                        "symbol": symbol,
                        "http_status": response.status_code,
                        "error": response.text[:500],
                        "options_data": all_rows,
                        "source": "alpaca_option_chain",
                    }

                payload = response.json()
                rows = cls.normalize_chain(
                    payload=payload,
                    underlying_symbol=symbol,
                    spot_price=spot_price,
                )

                all_rows.extend(rows)

                page_token = payload.get("next_page_token") if isinstance(payload, dict) else None
                pages += 1

                if not page_token:
                    break

            except Exception as exc:
                errors.append(str(exc))
                break

        status = "OK" if all_rows else "NO_OPTIONS_RETURNED"

        return {
            "status": status,
            "symbol": symbol,
            "options_data": all_rows,
            "rows": len(all_rows),
            "pages": pages,
            "feed": params.get("feed"),
            "source": "alpaca_option_chain",
            "errors": errors,
            "fetched_at": datetime.now(timezone.utc).isoformat(),
        }


__all__ = ["AlpacaOptionChainAdapter"]
