"""Comprehensive unit tests for portfolio advisor and allocation modules.

Tests advisor.py (suggestion engine) and allocation.py (shared logic)
with all external dependencies mocked.
"""
import json
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

import pytest

from stockpulse.portfolio.advisor import (
    AdvisorSuggestion,
    Severity,
    SuggestionType,
    _detect_state_changes,
    _evaluate_risk_actions,
    _evaluate_swap,
    _evaluate_watchlist,
    _evaluate_deployment,
    _evaluate_near_misses,
    _is_etf,
    _update_persistence,
    _check_turnover,
    _check_min_hold,
    _can_trim,
    evaluate,
    generate_eod_plan,
    acknowledge_suggestion,
)
from stockpulse.portfolio.allocation import (
    check_buy_eligible,
    check_watchlist_starter_eligible,
    compute_buy_size,
    compute_starter_size,
)

# ── Patch targets ───────────────────────────────────────────────
# Functions imported lazily inside advisor.py functions need to be
# patched at their source module, not at 'stockpulse.portfolio.advisor'.
_P_SETTINGS_STRATEGIES = "stockpulse.config.settings.load_strategies"
_P_SETTINGS_PORTFOLIO = "stockpulse.config.settings.load_portfolio"
_P_ALLOC_BUY_ELIGIBLE = "stockpulse.portfolio.allocation.check_buy_eligible"
_P_ALLOC_BUY_SIZE = "stockpulse.portfolio.allocation.compute_buy_size"
_P_ALLOC_STARTER_SIZE = "stockpulse.portfolio.allocation.compute_starter_size"
_P_ALLOC_WL_ELIGIBLE = "stockpulse.portfolio.allocation.check_watchlist_starter_eligible"
_P_RISK_CONC = "stockpulse.portfolio.risk.check_concentration_limits"
_P_ADV_SAVE = "stockpulse.portfolio.advisor._save_state"
_P_ADV_LOAD = "stockpulse.portfolio.advisor._load_state"
_P_ADV_CONFIG = "stockpulse.portfolio.advisor._get_config"
_P_ADV_CTX = "stockpulse.portfolio.advisor._get_portfolio_context"
_P_ADV_TAX = "stockpulse.portfolio.advisor._add_tax_annotations"
_P_ADV_EVAL = "stockpulse.portfolio.advisor.evaluate"
_P_ADV_SWAP = "stockpulse.portfolio.advisor._evaluate_swap"


# ── Fixtures / factory helpers ──────────────────────────────────


def _risk_check(allowed=True, sector="Tech", industry="Semis",
                cluster_tickers=None, size_multiplier=1.0):
    return {
        "allowed": allowed,
        "reasons": [] if allowed else ["blocked"],
        "size_multiplier": size_multiplier,
        "sector": sector,
        "industry": industry,
        "cluster_tickers": cluster_tickers or [],
    }


def _position(ticker, shares=10, entry_price=100.0, current_price=110.0,
              pnl_pct=10.0, entry_date="2024-06-01"):
    return {
        "ticker": ticker,
        "shares": shares,
        "entry_price": entry_price,
        "current_price": current_price,
        "current_value": shares * current_price,
        "invested": shares * entry_price,
        "pnl": shares * (current_price - entry_price),
        "pnl_pct": pnl_pct,
        "entry_date": entry_date,
    }


def _rec(ticker, action="BUY", score=65.0, confidence=60,
         thesis="strong momentum", signals=None, confirmation=None,
         invalidated=False):
    r = {
        "ticker": ticker,
        "action": action,
        "composite_score": score,
        "confidence": confidence,
        "thesis": thesis,
        "invalidated": invalidated,
    }
    if signals is not None:
        r["signals"] = signals
    if confirmation is not None:
        r["confirmation"] = confirmation
    return r


def _ctx(positions=None, cash=15000, total=100000, drawdown=None,
         clusters=None):
    positions = positions or []
    held = {p["ticker"] for p in positions}
    pv = sum(p.get("current_value", 0) for p in positions)
    if drawdown is None:
        drawdown = {"drawdown_pct": 0, "size_multiplier": 1.0, "new_buys_paused": False}
    return {
        "positions": positions,
        "portfolio_value": pv,
        "total_invested": sum(p.get("invested", 0) for p in positions),
        "cash_available": cash,
        "cash_pct": cash / total if total else 1.0,
        "clusters": clusters or {},
        "drawdown": drawdown,
        "held_tickers": held,
        "total": total,
    }


def _config(**overrides):
    cfg = {
        "evaluate_after_every_scan": True,
        "suggest_exit_on_sell": True,
        "suggest_trim_on_caution": {
            "enabled": True,
            "require_persistence_scans": 2,
            "trim_fraction": 0.25,
        },
        "suggest_swap_to_fund_buy": {
            "enabled": True,
            "max_swaps_per_day": 1,
            "incoming_min_score": 60,
            "require_persistence_scans": 2,
            "outgoing_max_tier": "HOLD",
            "min_score_gap": 20,
            "require_different_cluster": True,
        },
        "cash_reserve_min": 0.12,
        "allow_watchlist_starters": True,
        "never_swap_into_watchlist": True,
        "taxable_account_show_tax_impact": False,
        "show_wash_sale_warning": False,
        "turnover": {
            "min_hold_trading_days": 3,
            "max_trims_per_week_per_position": 2,
        },
    }
    cfg.update(overrides)
    return cfg


def _state(**overrides):
    s = {
        "last_run": None,
        "scan_trigger": None,
        "ticker_actions": {},
        "current_suggestions": [],
        "dispatched_hashes": {},
        "acknowledged_hashes": [],
        "turnover": {
            "swaps_today": 0,
            "swap_date": "",
            "trims_this_week": {},
            "last_trade_dates": {},
        },
    }
    s.update(overrides)
    return s


def _strategies(risk=None, allocation=None, portfolio_advisor=None):
    strat = {
        "risk": risk or {"max_positions": 8, "max_position_pct": 8},
        "allocation": allocation or {
            "watchlist_starter_min_score": 30,
            "max_watchlist_sleeve": 0.25,
            "max_watchlist_names": 3,
            "watchlist_starter_size": 0.33,
        },
    }
    if portfolio_advisor is not None:
        strat["portfolio_advisor"] = portfolio_advisor
    return strat


# ═══════════════════════════════════════════════════════════════
# allocation.py tests
# ═══════════════════════════════════════════════════════════════


class TestCheckBuyEligible:
    """Tests for allocation.check_buy_eligible."""

    @patch(_P_RISK_CONC)
    def test_passes_when_allowed(self, mock_conc):
        mock_conc.return_value = _risk_check(allowed=True)
        rec = _rec("NVDA", action="BUY", score=70)
        result = check_buy_eligible(rec, [], 100000, set(), max_positions=8)
        assert result is not None
        assert result["allowed"] is True

    @patch(_P_RISK_CONC)
    def test_fails_when_concentration_blocked(self, mock_conc):
        mock_conc.return_value = _risk_check(allowed=False)
        rec = _rec("NVDA", action="BUY", score=70)
        result = check_buy_eligible(rec, [], 100000, set(), max_positions=8)
        assert result is None

    @patch(_P_RISK_CONC)
    def test_passes_for_held_ticker_even_when_blocked(self, mock_conc):
        """Already-held tickers bypass concentration block."""
        mock_conc.return_value = _risk_check(allowed=False)
        rec = _rec("NVDA", action="BUY", score=70)
        held = {"NVDA"}
        result = check_buy_eligible(rec, [_position("NVDA")], 100000, held, max_positions=8)
        assert result is not None


class TestCheckWatchlistStarterEligible:
    """Tests for allocation.check_watchlist_starter_eligible -- all 7 qualifiers."""

    def _passing_rec(self, ticker="ACME"):
        return _rec(
            ticker, action="WATCHLIST", score=55, confidence=50,
            signals={
                "relative_strength": {"score": 75},
                "earnings": {"score": 10},
                "moving_averages": {"price_above_20ema": True},
            },
            confirmation={
                "buckets": {"trend": {"confirms": True}},
            },
            invalidated=False,
        )

    @patch(_P_RISK_CONC)
    def test_passes_all_seven(self, mock_conc):
        mock_conc.return_value = _risk_check(allowed=True)
        alloc_cfg = {"watchlist_starter_min_score": 30}
        result = check_watchlist_starter_eligible(
            self._passing_rec(), [], 100000, set(), alloc_cfg,
        )
        assert result["eligible"] is True
        assert result["reason"] is None

    def test_fails_score_too_low(self):
        rec = self._passing_rec()
        rec["composite_score"] = 20
        result = check_watchlist_starter_eligible(rec, [], 100000, set(),
                                                   {"watchlist_starter_min_score": 30})
        assert result["eligible"] is False
        assert "score" in result["reason"]
        assert result["near_miss"] is False

    @patch(_P_RISK_CONC)
    def test_fails_trend_not_confirming(self, mock_conc):
        rec = self._passing_rec()
        rec["confirmation"]["buckets"]["trend"]["confirms"] = False
        result = check_watchlist_starter_eligible(rec, [], 100000, set(),
                                                   {"watchlist_starter_min_score": 30})
        assert result["eligible"] is False
        assert "trend" in result["reason"]
        assert result["near_miss"] is True

    @patch(_P_RISK_CONC)
    def test_fails_rs_below_60(self, mock_conc):
        rec = self._passing_rec()
        rec["signals"]["relative_strength"]["score"] = 45
        result = check_watchlist_starter_eligible(rec, [], 100000, set(),
                                                   {"watchlist_starter_min_score": 30})
        assert result["eligible"] is False
        assert "RS" in result["reason"]
        assert result["near_miss"] is True
        assert "45" in result["near_miss_detail"]

    def test_fails_earnings_blackout(self):
        rec = self._passing_rec()
        rec["signals"]["earnings"]["score"] = -40
        result = check_watchlist_starter_eligible(rec, [], 100000, set(),
                                                   {"watchlist_starter_min_score": 30})
        assert result["eligible"] is False
        assert "earnings" in result["reason"]
        assert result["near_miss"] is False

    @patch(_P_RISK_CONC)
    def test_fails_concentration_limits(self, mock_conc):
        mock_conc.return_value = _risk_check(allowed=False)
        rec = self._passing_rec()
        result = check_watchlist_starter_eligible(rec, [], 100000, set(),
                                                   {"watchlist_starter_min_score": 30})
        assert result["eligible"] is False
        assert "concentration" in result["reason"]

    @patch(_P_RISK_CONC)
    def test_fails_cluster_overlap(self, mock_conc):
        mock_conc.return_value = _risk_check(allowed=True, cluster_tickers=["PEER"])
        rec = self._passing_rec()
        clusters_used = {"PEER"}
        result = check_watchlist_starter_eligible(
            rec, [], 100000, set(),
            {"watchlist_starter_min_score": 30}, clusters_used,
        )
        assert result["eligible"] is False
        assert "cluster" in result["reason"]

    @patch(_P_RISK_CONC)
    def test_fails_price_below_20ema(self, mock_conc):
        mock_conc.return_value = _risk_check(allowed=True)
        rec = self._passing_rec()
        rec["signals"]["moving_averages"]["price_above_20ema"] = False
        result = check_watchlist_starter_eligible(rec, [], 100000, set(),
                                                   {"watchlist_starter_min_score": 30})
        assert result["eligible"] is False
        assert "20 EMA" in result["reason"]
        assert result["near_miss"] is True

    @patch(_P_RISK_CONC)
    def test_fails_invalidated(self, mock_conc):
        mock_conc.return_value = _risk_check(allowed=True)
        rec = self._passing_rec()
        rec["invalidated"] = True
        result = check_watchlist_starter_eligible(rec, [], 100000, set(),
                                                   {"watchlist_starter_min_score": 30})
        assert result["eligible"] is False
        assert "invalidated" in result["reason"]


class TestComputeBuySize:
    """Tests for allocation.compute_buy_size."""

    def test_basic_sizing(self):
        risk_cfg = {"max_position_pct": 8}
        result = compute_buy_size(100000, score=55.0, risk_cfg=risk_cfg)
        # max_pct=0.08, score_factor=min(55/55,1.0)=1.0, mult=1.0
        assert result == pytest.approx(8000.0)

    def test_low_score_reduces_size(self):
        risk_cfg = {"max_position_pct": 8}
        result = compute_buy_size(100000, score=27.5, risk_cfg=risk_cfg)
        # score_factor = 27.5/55 = 0.5
        assert result == pytest.approx(4000.0)

    def test_size_multiplier_halves(self):
        risk_cfg = {"max_position_pct": 8}
        result = compute_buy_size(100000, score=55.0, risk_cfg=risk_cfg, size_multiplier=0.5)
        assert result == pytest.approx(4000.0)

    def test_score_factor_capped_at_one(self):
        risk_cfg = {"max_position_pct": 8}
        result = compute_buy_size(100000, score=110.0, risk_cfg=risk_cfg)
        # score_factor = min(110/55, 1.0) = 1.0
        assert result == pytest.approx(8000.0)


class TestComputeStarterSize:
    """Tests for allocation.compute_starter_size."""

    def test_default_33_pct(self):
        alloc_cfg = {"watchlist_starter_size": 0.33}
        result = compute_starter_size(6000.0, alloc_cfg)
        assert result == pytest.approx(1980.0)

    def test_capped_by_remaining_cash(self):
        alloc_cfg = {"watchlist_starter_size": 0.33}
        result = compute_starter_size(6000.0, alloc_cfg, remaining=500.0)
        assert result == pytest.approx(500.0)

    def test_capped_by_sleeve_remaining(self):
        alloc_cfg = {"watchlist_starter_size": 0.33}
        result = compute_starter_size(6000.0, alloc_cfg, sleeve_remaining=800.0)
        assert result == pytest.approx(800.0)


# ═══════════════════════════════════════════════════════════════
# advisor.py tests
# ═══════════════════════════════════════════════════════════════


class TestSellSignalExit:
    """SELL signal generates URGENT EXIT suggestion."""

    def test_sell_generates_exit(self):
        pos = _position("AAPL", pnl_pct=-5.0)
        ctx = _ctx(positions=[pos])
        rec_map = {"AAPL": _rec("AAPL", action="SELL", score=-30)}
        state = _state(ticker_actions={"AAPL": {"action": "SELL", "scan_count": 1}})
        config = _config()

        with patch(_P_SETTINGS_STRATEGIES, return_value=_strategies()):
            results = _evaluate_risk_actions(ctx, rec_map, state, config)

        assert len(results) >= 1
        exit_sug = [s for s in results if s.suggestion_type == SuggestionType.EXIT]
        assert len(exit_sug) == 1
        assert exit_sug[0].severity == Severity.URGENT
        assert exit_sug[0].ticker == "AAPL"
        assert exit_sug[0].action == "SELL"
        assert exit_sug[0].suggested_amount == pos["current_value"]


class TestCautionPersistence:
    """CAUTION requires persistence before generating TRIM."""

    def test_caution_scan1_no_trim(self):
        """scan_count=1 with require_persistence_scans=2: no trim yet."""
        pos = _position("MSFT")
        ctx = _ctx(positions=[pos])
        rec_map = {"MSFT": _rec("MSFT", action="CAUTION", score=-15)}
        state = _state(
            ticker_actions={"MSFT": {"action": "CAUTION", "scan_count": 1, "eod_count": 0}},
        )
        config = _config()

        with patch(_P_SETTINGS_STRATEGIES, return_value=_strategies()):
            results = _evaluate_risk_actions(ctx, rec_map, state, config)

        trims = [s for s in results if s.suggestion_type == SuggestionType.TRIM_CAUTION]
        assert len(trims) == 0

    def test_caution_scan2_generates_trim(self):
        """eod_count=1 (persisted 1 EOD) -> ACTIONABLE TRIM."""
        pos = _position("MSFT", current_price=100, shares=10)
        ctx = _ctx(positions=[pos])
        rec_map = {"MSFT": _rec("MSFT", action="CAUTION", score=-15)}
        state = _state(
            ticker_actions={"MSFT": {"action": "CAUTION", "scan_count": 6, "eod_count": 1}},
        )
        config = _config()

        with patch(_P_SETTINGS_STRATEGIES, return_value=_strategies()):
            results = _evaluate_risk_actions(ctx, rec_map, state, config)

        trims = [s for s in results if s.suggestion_type == SuggestionType.TRIM_CAUTION]
        assert len(trims) == 1
        assert trims[0].severity == Severity.ACTIONABLE
        assert trims[0].trim_fraction == 0.25
        assert trims[0].suggested_amount == pytest.approx(250.0)  # 1000 * 0.25

    def test_caution_eod1_generates_trim(self):
        """eod_count=1 is enough even at scan_count=1."""
        pos = _position("MSFT", current_price=100, shares=10)
        ctx = _ctx(positions=[pos])
        rec_map = {"MSFT": _rec("MSFT", action="CAUTION", score=-15)}
        state = _state(
            ticker_actions={"MSFT": {"action": "CAUTION", "scan_count": 1, "eod_count": 1}},
        )
        config = _config()

        with patch(_P_SETTINGS_STRATEGIES, return_value=_strategies()):
            results = _evaluate_risk_actions(ctx, rec_map, state, config)

        trims = [s for s in results if s.suggestion_type == SuggestionType.TRIM_CAUTION]
        assert len(trims) == 1


class TestBuyFromCash:
    """BUY candidate with cash above reserve -> BUY_FROM_CASH."""

    @patch(_P_SETTINGS_STRATEGIES)
    @patch(_P_ALLOC_BUY_SIZE)
    @patch(_P_ALLOC_BUY_ELIGIBLE)
    def test_buy_from_cash_when_above_reserve(self, mock_eligible, mock_size, mock_strat):
        mock_eligible.return_value = _risk_check(allowed=True)
        mock_size.return_value = 5000.0
        mock_strat.return_value = _strategies()

        # cash=15000, total=100000, reserve=12% -> deployable = 15000 - 12000 = 3000
        ctx = _ctx(cash=15000, total=100000)
        rec_map = {"NVDA": _rec("NVDA", action="BUY", score=70)}
        state = _state()
        config = _config()

        results = _evaluate_deployment(ctx, rec_map, state, config, freed_cash=0)

        buys = [s for s in results if s.suggestion_type == SuggestionType.BUY_FROM_CASH]
        assert len(buys) == 1
        assert buys[0].ticker == "NVDA"
        assert buys[0].severity == Severity.ACTIONABLE
        # Amount should be min(5000, 3000) = 3000
        assert buys[0].suggested_amount == pytest.approx(3000.0)


class TestBuyNoCashTriggersSwap:
    """BUY candidate with no deployable cash -> evaluate SWAP."""

    @patch(_P_SETTINGS_STRATEGIES)
    @patch(_P_ALLOC_BUY_SIZE)
    @patch(_P_ALLOC_BUY_ELIGIBLE)
    @patch(_P_ADV_SWAP)
    def test_no_cash_evaluates_swap(self, mock_swap, mock_eligible, mock_size, mock_strat):
        mock_eligible.return_value = _risk_check(allowed=True)
        mock_size.return_value = 5000.0
        mock_strat.return_value = _strategies()
        mock_swap.return_value = AdvisorSuggestion(
            severity=Severity.ACTIONABLE,
            suggestion_type=SuggestionType.SWAP,
            ticker="NVDA",
            action="SWAP",
            summary="swap",
            details="details",
            swap_out_ticker="WEAK",
        )

        # cash=5000, total=100000, reserve=12% -> deployable = 5000 - 12000 = -7000 (negative)
        ctx = _ctx(cash=5000, total=100000)
        rec_map = {"NVDA": _rec("NVDA", action="BUY", score=70)}
        state = _state()
        config = _config()

        results = _evaluate_deployment(ctx, rec_map, state, config, freed_cash=0)

        mock_swap.assert_called_once()
        swaps = [s for s in results if s.suggestion_type == SuggestionType.SWAP]
        assert len(swaps) == 1


class TestSwapBlockedByScoreGap:
    """SWAP blocked when score gap < min_score_gap (20)."""

    def test_gap_too_small(self):
        pos_weak = _position("WEAK", current_price=50, shares=20)
        ctx = _ctx(positions=[pos_weak], cash=0, total=100000)
        # incoming 65, outgoing 50 -> gap=15 < 20
        rec_map = {
            "NVDA": _rec("NVDA", action="BUY", score=65),
            "WEAK": _rec("WEAK", action="HOLD", score=50),
        }
        state = _state(
            ticker_actions={"NVDA": {"action": "BUY", "scan_count": 3}},
            turnover={"swaps_today": 0, "swap_date": "", "trims_this_week": {}, "last_trade_dates": {}},
        )
        config = _config()

        result = _evaluate_swap(ctx, rec_map, state, config, "NVDA", rec_map["NVDA"])
        assert result is None


class TestSwapBlockedBySameCluster:
    """SWAP blocked when incoming and outgoing in the same cluster."""

    def test_same_cluster_blocked(self):
        pos_weak = _position("AMD", current_price=50, shares=20)
        ctx = _ctx(
            positions=[pos_weak], cash=0, total=100000,
            clusters={"semis": ["NVDA", "AMD"]},
        )
        # gap is >20 but they share a cluster
        rec_map = {
            "NVDA": _rec("NVDA", action="BUY", score=80),
            "AMD": _rec("AMD", action="HOLD", score=30),
        }
        state = _state(
            ticker_actions={"NVDA": {"action": "BUY", "scan_count": 3}},
            turnover={"swaps_today": 0, "swap_date": "", "trims_this_week": {}, "last_trade_dates": {}},
        )
        config = _config()

        result = _evaluate_swap(ctx, rec_map, state, config, "NVDA", rec_map["NVDA"])
        assert result is None


class TestSwapBlockedByMaxPerDay:
    """SWAP blocked when max swaps per day already reached."""

    def test_max_swaps_hit(self):
        pos_weak = _position("WEAK", current_price=50, shares=20)
        ctx = _ctx(positions=[pos_weak], cash=0, total=100000)
        rec_map = {
            "NVDA": _rec("NVDA", action="BUY", score=80),
            "WEAK": _rec("WEAK", action="HOLD", score=30),
        }
        today = datetime.now().strftime("%Y-%m-%d")
        state = _state(
            ticker_actions={"NVDA": {"action": "BUY", "scan_count": 3}},
            turnover={"swaps_today": 1, "swap_date": today, "trims_this_week": {}, "last_trade_dates": {}},
        )
        config = _config()

        result = _evaluate_swap(ctx, rec_map, state, config, "NVDA", rec_map["NVDA"])
        assert result is None


class TestSwapSuccess:
    """SWAP succeeds when all conditions met."""

    def test_swap_generated(self):
        pos_weak = _position("WEAK", current_price=50, shares=20, pnl_pct=-5.0)
        ctx = _ctx(positions=[pos_weak], cash=0, total=100000)
        rec_map = {
            "NVDA": _rec("NVDA", action="BUY", score=80),
            "WEAK": _rec("WEAK", action="HOLD", score=30),
        }
        state = _state(
            ticker_actions={"NVDA": {"action": "BUY", "scan_count": 3}},
            turnover={"swaps_today": 0, "swap_date": "", "trims_this_week": {}, "last_trade_dates": {}},
        )
        config = _config()

        result = _evaluate_swap(ctx, rec_map, state, config, "NVDA", rec_map["NVDA"])
        assert result is not None
        assert result.suggestion_type == SuggestionType.SWAP
        assert result.ticker == "NVDA"
        assert result.swap_out_ticker == "WEAK"
        assert result.swap_score_gap == pytest.approx(50.0)


class TestWatchlistStarter:
    """WATCHLIST starter passes/fails the 7 qualifiers via advisor."""

    def _wl_rec(self, ticker="ACME", score=55, rs=75, trend_confirms=True,
                earnings_score=10, price_above_20ema=True, invalidated=False):
        return _rec(
            ticker, action="WATCHLIST", score=score, confidence=50,
            signals={
                "relative_strength": {"score": rs},
                "earnings": {"score": earnings_score},
                "moving_averages": {"price_above_20ema": price_above_20ema},
            },
            confirmation={"buckets": {"trend": {"confirms": trend_confirms}}},
            invalidated=invalidated,
        )

    @patch(_P_ALLOC_WL_ELIGIBLE)
    @patch(_P_ALLOC_STARTER_SIZE)
    @patch(_P_ALLOC_BUY_SIZE)
    @patch(_P_SETTINGS_STRATEGIES)
    def test_watchlist_starter_passes(self, mock_strat, mock_buy_size,
                                      mock_starter_size, mock_eligible):
        mock_strat.return_value = _strategies()
        mock_eligible.return_value = {
            "eligible": True, "risk_check": _risk_check(), "cluster_key": frozenset(),
            "reason": None, "near_miss": False,
        }
        mock_buy_size.return_value = 6000.0
        mock_starter_size.return_value = 1980.0

        ctx = _ctx(cash=20000, total=100000)
        rec_map = {"ACME": self._wl_rec()}
        state = _state()
        config = _config()

        results = _evaluate_watchlist(ctx, rec_map, state, config)

        starters = [s for s in results if s.suggestion_type == SuggestionType.WATCHLIST_STARTER]
        assert len(starters) == 1
        assert starters[0].ticker == "ACME"
        assert starters[0].severity == Severity.ACTIONABLE
        assert starters[0].suggested_amount == pytest.approx(1980.0)

    @patch(_P_ALLOC_WL_ELIGIBLE)
    @patch(_P_SETTINGS_STRATEGIES)
    def test_watchlist_starter_fails_rs(self, mock_strat, mock_eligible):
        """RS < 60 -> rejected by qualifier check."""
        mock_strat.return_value = _strategies()
        mock_eligible.return_value = {
            "eligible": False, "reason": "RS 45 < 60",
            "near_miss": True, "near_miss_detail": "relative strength 45/60",
        }

        ctx = _ctx(cash=20000, total=100000)
        rec_map = {"ACME": self._wl_rec(rs=45)}
        state = _state()
        config = _config()

        results = _evaluate_watchlist(ctx, rec_map, state, config)

        starters = [s for s in results if s.suggestion_type == SuggestionType.WATCHLIST_STARTER]
        assert len(starters) == 0


class TestNearMiss:
    """Near-miss tickers appear as INFO severity."""

    @patch(_P_ALLOC_WL_ELIGIBLE)
    @patch(_P_SETTINGS_STRATEGIES)
    def test_near_miss_shows_as_info(self, mock_strat, mock_eligible):
        mock_strat.return_value = _strategies()
        mock_eligible.return_value = {
            "eligible": False, "reason": "RS 55 < 60",
            "near_miss": True, "near_miss_detail": "relative strength 55/60",
        }

        ctx = _ctx(cash=20000, total=100000)
        rec_map = {
            "ALMOST": _rec("ALMOST", action="WATCHLIST", score=45),
        }
        already_suggested = set()

        results = _evaluate_near_misses(ctx, rec_map, _state(), _config(), already_suggested)

        assert len(results) == 1
        assert results[0].severity == Severity.INFORMATIONAL
        assert results[0].suggestion_type == SuggestionType.NEAR_MISS
        assert results[0].ticker == "ALMOST"

    @patch(_P_ALLOC_WL_ELIGIBLE)
    @patch(_P_SETTINGS_STRATEGIES)
    def test_near_miss_skips_eligible(self, mock_strat, mock_eligible):
        """If the ticker is actually eligible, it should not appear as near-miss."""
        mock_strat.return_value = _strategies()
        mock_eligible.return_value = {
            "eligible": True, "reason": None, "near_miss": False,
        }

        ctx = _ctx(cash=20000, total=100000)
        rec_map = {"GOOD": _rec("GOOD", action="WATCHLIST", score=50)}

        results = _evaluate_near_misses(ctx, rec_map, _state(), _config(), set())
        assert len(results) == 0


class TestEtfSkipsConcentration:
    """ETF tickers skip single-position concentration check."""

    def test_etf_no_concentration_trim(self):
        """SPY at 15% weight should NOT get a concentration TRIM."""
        pos = _position("SPY", shares=150, current_price=100)  # 15000
        ctx = _ctx(positions=[pos], total=100000)
        rec_map = {"SPY": _rec("SPY", action="HOLD", score=10)}
        state = _state()
        config = _config()

        with patch(_P_SETTINGS_STRATEGIES,
                   return_value=_strategies(risk={"max_position_pct": 8})):
            results = _evaluate_risk_actions(ctx, rec_map, state, config)

        conc_trims = [s for s in results if s.suggestion_type == SuggestionType.TRIM_CONCENTRATION]
        assert len(conc_trims) == 0

    def test_non_etf_gets_concentration_trim(self):
        """Non-ETF at 15% weight SHOULD get a concentration TRIM."""
        pos = _position("NVDA", shares=150, current_price=100)  # 15000
        ctx = _ctx(positions=[pos], total=100000)
        rec_map = {"NVDA": _rec("NVDA", action="HOLD", score=10)}
        state = _state()
        config = _config()

        with patch(_P_SETTINGS_STRATEGIES,
                   return_value=_strategies(risk={"max_position_pct": 8})):
            results = _evaluate_risk_actions(ctx, rec_map, state, config)

        conc_trims = [s for s in results if s.suggestion_type == SuggestionType.TRIM_CONCENTRATION]
        assert len(conc_trims) == 1
        assert conc_trims[0].ticker == "NVDA"


class TestDrawdownPaused:
    """Drawdown paused -> no deployment suggestions."""

    @patch(_P_SETTINGS_STRATEGIES)
    @patch(_P_ALLOC_BUY_ELIGIBLE)
    def test_drawdown_paused_blocks_buys(self, mock_eligible, mock_strat):
        mock_strat.return_value = _strategies()
        mock_eligible.return_value = _risk_check(allowed=True)

        ctx = _ctx(
            cash=20000, total=100000,
            drawdown={"drawdown_pct": 15.0, "size_multiplier": 0.5, "new_buys_paused": True},
        )
        rec_map = {"NVDA": _rec("NVDA", action="BUY", score=70)}
        state = _state()
        config = _config()

        results = _evaluate_deployment(ctx, rec_map, state, config, freed_cash=0)
        assert len(results) == 0

    def test_drawdown_generates_risk_alert(self):
        """Drawdown pause also generates a RISK_ALERT."""
        ctx = _ctx(
            positions=[],
            drawdown={"drawdown_pct": 15.0, "size_multiplier": 0.5, "new_buys_paused": True},
        )
        rec_map = {}
        state = _state()
        config = _config()

        with patch(_P_SETTINGS_STRATEGIES, return_value=_strategies()):
            results = _evaluate_risk_actions(ctx, rec_map, state, config)

        alerts = [s for s in results if s.suggestion_type == SuggestionType.RISK_ALERT]
        assert len(alerts) == 1
        assert alerts[0].severity == Severity.URGENT
        assert "PAUSE" in alerts[0].action


class TestStateChangeDetection:
    """State change detection: new vs repeat suggestions."""

    def test_new_suggestion_flagged_is_new(self):
        s = AdvisorSuggestion(
            severity=Severity.ACTIONABLE,
            suggestion_type=SuggestionType.BUY_FROM_CASH,
            ticker="NVDA",
            action="BUY",
            summary="buy",
            details="details",
        )
        state = _state(dispatched_hashes={})
        results = _detect_state_changes([s], state)
        assert len(results) == 1
        assert results[0].is_new is True

    def test_repeat_suggestion_flagged_not_new(self):
        s = AdvisorSuggestion(
            severity=Severity.ACTIONABLE,
            suggestion_type=SuggestionType.BUY_FROM_CASH,
            ticker="NVDA",
            action="BUY",
            summary="buy",
            details="details",
        )
        state = _state(dispatched_hashes={s.hash: "2025-01-01T00:00:00"})
        results = _detect_state_changes([s], state)
        assert len(results) == 1
        assert results[0].is_new is False


class TestAcknowledgedFiltering:
    """Acknowledged suggestions are filtered out."""

    def test_acknowledged_removed(self):
        s = AdvisorSuggestion(
            severity=Severity.ACTIONABLE,
            suggestion_type=SuggestionType.EXIT,
            ticker="AAPL",
            action="SELL",
            summary="exit",
            details="details",
        )
        state = _state(acknowledged_hashes=[s.hash])
        results = _detect_state_changes([s], state)
        assert len(results) == 0

    def test_non_acknowledged_kept(self):
        s = AdvisorSuggestion(
            severity=Severity.ACTIONABLE,
            suggestion_type=SuggestionType.EXIT,
            ticker="AAPL",
            action="SELL",
            summary="exit",
            details="details",
        )
        state = _state(acknowledged_hashes=["some_other_hash"])
        results = _detect_state_changes([s], state)
        assert len(results) == 1


class TestEodPlan:
    """EOD plan generates consolidated summary."""

    @patch(_P_ADV_SAVE)
    @patch(_P_ADV_EVAL)
    @patch(_P_ADV_LOAD, return_value=_state())
    @patch(_P_ADV_CONFIG, return_value=_config())
    def test_eod_plan_structure(self, mock_cfg, mock_load, mock_eval, mock_save):
        exit_sug = AdvisorSuggestion(
            severity=Severity.URGENT,
            suggestion_type=SuggestionType.EXIT,
            ticker="AAPL", action="SELL",
            summary="exit AAPL", details="",
            suggested_amount=5000,
        )
        buy_sug = AdvisorSuggestion(
            severity=Severity.ACTIONABLE,
            suggestion_type=SuggestionType.BUY_FROM_CASH,
            ticker="NVDA", action="BUY",
            summary="buy NVDA", details="",
            suggested_amount=3000,
        )
        mock_eval.return_value = [exit_sug, buy_sug]

        plan = generate_eod_plan([])

        assert "timestamp" in plan
        assert "summary" in plan
        assert plan["total_suggestions"] == 2
        assert plan["urgent_count"] == 1
        assert plan["actionable_count"] == 1
        assert plan["cash_freed"] == pytest.approx(5000.0)
        assert plan["cash_deployed"] == pytest.approx(3000.0)
        assert plan["net_cash_impact"] == pytest.approx(2000.0)
        assert len(plan["sections"]) >= 2

    @patch(_P_ADV_SAVE)
    @patch(_P_ADV_EVAL)
    @patch(_P_ADV_LOAD, return_value=_state())
    @patch(_P_ADV_CONFIG, return_value=_config())
    def test_eod_plan_no_suggestions(self, mock_cfg, mock_load, mock_eval, mock_save):
        mock_eval.return_value = []
        plan = generate_eod_plan([])
        assert "No changes recommended" in plan["summary"]
        assert plan["total_suggestions"] == 0


# ── Helper / utility tests ─────────────────────────────────────


class TestIsEtf:
    def test_known_etfs(self):
        assert _is_etf("SPY") is True
        assert _is_etf("QQQ") is True
        assert _is_etf("HLAL") is True

    def test_case_insensitive(self):
        assert _is_etf("spy") is True

    def test_non_etf(self):
        assert _is_etf("AAPL") is False
        assert _is_etf("NVDA") is False


class TestUpdatePersistence:
    def test_new_action_starts_at_1(self):
        state = _state()
        rec_map = {"AAPL": {"action": "CAUTION", "composite_score": -10}}
        result = _update_persistence(state, rec_map, {"AAPL"}, "manual")
        assert result["ticker_actions"]["AAPL"]["scan_count"] == 1
        assert result["ticker_actions"]["AAPL"]["eod_count"] == 0

    def test_same_action_increments(self):
        state = _state(
            ticker_actions={"AAPL": {"action": "CAUTION", "scan_count": 2, "eod_count": 0, "last_score": -10}},
        )
        rec_map = {"AAPL": {"action": "CAUTION", "composite_score": -12}}
        result = _update_persistence(state, rec_map, {"AAPL"}, "manual")
        assert result["ticker_actions"]["AAPL"]["scan_count"] == 3

    def test_eod_trigger_increments_eod_count(self):
        state = _state(
            ticker_actions={"AAPL": {"action": "CAUTION", "scan_count": 1, "eod_count": 0, "last_score": -10}},
        )
        rec_map = {"AAPL": {"action": "CAUTION", "composite_score": -10}}
        result = _update_persistence(state, rec_map, {"AAPL"}, "eod")
        assert result["ticker_actions"]["AAPL"]["eod_count"] == 1

    def test_action_change_resets(self):
        state = _state(
            ticker_actions={"AAPL": {"action": "BUY", "scan_count": 5, "eod_count": 2, "last_score": 50}},
        )
        rec_map = {"AAPL": {"action": "CAUTION", "composite_score": -10}}
        result = _update_persistence(state, rec_map, {"AAPL"}, "manual")
        assert result["ticker_actions"]["AAPL"]["scan_count"] == 1
        assert result["ticker_actions"]["AAPL"]["action"] == "CAUTION"

    def test_cleaned_up_when_no_longer_relevant(self):
        state = _state(
            ticker_actions={"OLD": {"action": "HOLD", "scan_count": 3, "eod_count": 1, "last_score": 5}},
        )
        rec_map = {}
        result = _update_persistence(state, rec_map, set(), "manual")
        assert "OLD" not in result["ticker_actions"]


class TestCheckTurnover:
    def test_can_swap_when_under_limit(self):
        state = _state(
            turnover={"swaps_today": 0, "swap_date": "", "trims_this_week": {}, "last_trade_dates": {}},
        )
        config = _config()
        result = _check_turnover(state, config)
        assert result["can_swap"] is True

    def test_cannot_swap_when_at_limit(self):
        today = datetime.now().strftime("%Y-%m-%d")
        state = _state(
            turnover={"swaps_today": 1, "swap_date": today, "trims_this_week": {}, "last_trade_dates": {}},
        )
        config = _config()
        result = _check_turnover(state, config)
        assert result["can_swap"] is False

    def test_resets_on_new_day(self):
        state = _state(
            turnover={"swaps_today": 1, "swap_date": "2020-01-01", "trims_this_week": {}, "last_trade_dates": {}},
        )
        config = _config()
        result = _check_turnover(state, config)
        assert result["can_swap"] is True


class TestCheckMinHold:
    def test_risk_action_always_passes(self):
        state = _state(
            turnover={"last_trade_dates": {"AAPL": datetime.now().strftime("%Y-%m-%d")}},
        )
        assert _check_min_hold(state, "AAPL", _config(), is_risk=True) is True

    def test_recent_trade_blocks(self):
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        state = _state(
            turnover={"last_trade_dates": {"AAPL": yesterday}},
        )
        assert _check_min_hold(state, "AAPL", _config(), is_risk=False) is False

    def test_old_trade_passes(self):
        old_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
        state = _state(
            turnover={"last_trade_dates": {"AAPL": old_date}},
        )
        assert _check_min_hold(state, "AAPL", _config(), is_risk=False) is True

    def test_no_record_passes(self):
        state = _state()
        assert _check_min_hold(state, "AAPL", _config(), is_risk=False) is True


class TestCanTrim:
    def test_allowed_when_under_limit(self):
        state = _state()
        assert _can_trim(state, "AAPL", _config()) is True

    def test_blocked_when_at_limit(self):
        current_week = datetime.now().strftime("%G-W%V")
        state = _state(
            turnover={"trims_this_week": {"AAPL": {"week_iso": current_week, "count": 2}}},
        )
        assert _can_trim(state, "AAPL", _config()) is False


class TestAdvisorSuggestionHash:
    """Hash generation for state tracking."""

    def test_hash_auto_generated(self):
        s = AdvisorSuggestion(
            severity=Severity.URGENT,
            suggestion_type=SuggestionType.EXIT,
            ticker="AAPL",
            action="SELL",
            summary="exit",
            details="",
        )
        assert s.hash == "exit_AAPL"

    def test_swap_hash_includes_out_ticker(self):
        s = AdvisorSuggestion(
            severity=Severity.ACTIONABLE,
            suggestion_type=SuggestionType.SWAP,
            ticker="NVDA",
            action="SWAP",
            summary="swap",
            details="",
            swap_out_ticker="WEAK",
        )
        assert s.hash == "swap_NVDA_WEAK"

    def test_to_dict_serializes_enums(self):
        s = AdvisorSuggestion(
            severity=Severity.URGENT,
            suggestion_type=SuggestionType.EXIT,
            ticker="X",
            action="SELL",
            summary="s",
            details="d",
        )
        d = s.to_dict()
        assert d["severity"] == "urgent"
        assert d["suggestion_type"] == "exit"


class TestAcknowledgeSuggestion:
    """Test the acknowledge_suggestion public API."""

    @patch(_P_ADV_SAVE)
    @patch(_P_ADV_LOAD)
    def test_acknowledge_new_hash(self, mock_load, mock_save):
        mock_load.return_value = _state(
            current_suggestions=[{"hash": "exit_AAPL", "ticker": "AAPL"}],
        )
        result = acknowledge_suggestion("exit_AAPL")
        assert result is True
        saved = mock_save.call_args[0][0]
        assert "exit_AAPL" in saved["acknowledged_hashes"]
        assert len(saved["current_suggestions"]) == 0

    @patch(_P_ADV_SAVE)
    @patch(_P_ADV_LOAD)
    def test_acknowledge_already_acked(self, mock_load, mock_save):
        mock_load.return_value = _state(acknowledged_hashes=["exit_AAPL"])
        result = acknowledge_suggestion("exit_AAPL")
        assert result is False


# ── Integration-level test: full evaluate() ─────────────────────


class TestEvaluateIntegration:
    """End-to-end test of evaluate() with all dependencies mocked."""

    @patch(_P_ADV_SAVE)
    @patch(_P_ADV_LOAD)
    @patch(_P_ADV_CONFIG)
    @patch(_P_ADV_CTX)
    @patch(_P_ADV_TAX, side_effect=lambda s, *a: s)
    def test_sell_flows_through_evaluate(self, mock_tax, mock_ctx, mock_cfg,
                                         mock_load, mock_save):
        pos = _position("AAPL", pnl_pct=-10.0)
        mock_ctx.return_value = _ctx(positions=[pos], total=100000)
        mock_cfg.return_value = _config()
        mock_load.return_value = _state()

        recs = [_rec("AAPL", action="SELL", score=-40)]

        with patch(_P_SETTINGS_STRATEGIES, return_value=_strategies()):
            results = evaluate(recs, scan_trigger="manual")

        exits = [s for s in results if s.suggestion_type == SuggestionType.EXIT]
        assert len(exits) == 1
        assert exits[0].severity == Severity.URGENT

        # State was saved
        mock_save.assert_called_once()

    @patch(_P_ADV_SAVE)
    @patch(_P_ADV_LOAD)
    @patch(_P_ADV_CONFIG)
    @patch(_P_ADV_CTX)
    @patch(_P_ADV_TAX, side_effect=lambda s, *a: s)
    def test_suggestions_sorted_by_severity_then_type(self, mock_tax, mock_ctx,
                                                       mock_cfg, mock_load, mock_save):
        """Verify priority ordering: URGENT EXIT before ACTIONABLE BUY."""
        pos = _position("AAPL", pnl_pct=-10.0)
        mock_ctx.return_value = _ctx(positions=[pos], cash=20000, total=100000)
        mock_cfg.return_value = _config()
        mock_load.return_value = _state()

        recs = [
            _rec("AAPL", action="SELL", score=-40),
            _rec("NVDA", action="BUY", score=70),
        ]

        with patch(_P_SETTINGS_STRATEGIES, return_value=_strategies()), \
             patch(_P_ALLOC_BUY_ELIGIBLE, return_value=_risk_check(allowed=True)), \
             patch(_P_ALLOC_BUY_SIZE, return_value=5000.0):
            results = evaluate(recs, scan_trigger="manual")

        # First should be EXIT (urgent), then BUY (actionable)
        assert len(results) >= 2
        assert results[0].suggestion_type == SuggestionType.EXIT
        assert results[0].severity == Severity.URGENT

    @patch(_P_ADV_SAVE)
    @patch(_P_ADV_LOAD)
    @patch(_P_ADV_CONFIG)
    @patch(_P_ADV_CTX)
    @patch(_P_ADV_TAX, side_effect=lambda s, *a: s)
    def test_evaluate_disabled_non_manual(self, mock_tax, mock_ctx, mock_cfg,
                                          mock_load, mock_save):
        """When evaluate_after_every_scan=False, non-manual triggers return empty."""
        mock_cfg.return_value = _config(evaluate_after_every_scan=False)

        results = evaluate([], scan_trigger="scheduled")
        assert results == []
        mock_ctx.assert_not_called()


class TestDrawdownWarningHalfSize:
    """Drawdown warning (not paused) generates ACTIONABLE risk alert."""

    def test_drawdown_warning_alert(self):
        ctx = _ctx(
            positions=[],
            drawdown={"drawdown_pct": 9.0, "size_multiplier": 0.5, "new_buys_paused": False},
        )
        rec_map = {}
        state = _state()
        config = _config()

        with patch(_P_SETTINGS_STRATEGIES, return_value=_strategies()):
            results = _evaluate_risk_actions(ctx, rec_map, state, config)

        alerts = [s for s in results if s.suggestion_type == SuggestionType.RISK_ALERT]
        assert len(alerts) == 1
        assert alerts[0].severity == Severity.ACTIONABLE
        assert "REDUCE" in alerts[0].action


class TestSwapPersistenceRequired:
    """SWAP requires incoming ticker to have persisted enough scans."""

    def test_swap_blocked_insufficient_persistence(self):
        pos_weak = _position("WEAK", current_price=50, shares=20)
        ctx = _ctx(positions=[pos_weak], cash=0, total=100000)
        rec_map = {
            "NVDA": _rec("NVDA", action="BUY", score=80),
            "WEAK": _rec("WEAK", action="HOLD", score=30),
        }
        # scan_count=1 < require_persistence_scans=2
        state = _state(
            ticker_actions={"NVDA": {"action": "BUY", "scan_count": 1}},
            turnover={"swaps_today": 0, "swap_date": "", "trims_this_week": {}, "last_trade_dates": {}},
        )
        config = _config()

        result = _evaluate_swap(ctx, rec_map, state, config, "NVDA", rec_map["NVDA"])
        assert result is None


class TestSwapDisabled:
    """SWAP disabled via config returns None."""

    def test_swap_disabled(self):
        ctx = _ctx(positions=[_position("WEAK")], cash=0, total=100000)
        rec_map = {"NVDA": _rec("NVDA", action="BUY", score=80)}
        config = _config()
        config["suggest_swap_to_fund_buy"]["enabled"] = False
        state = _state()

        result = _evaluate_swap(ctx, rec_map, state, config, "NVDA", rec_map["NVDA"])
        assert result is None


class TestSwapIncomingScoreTooLow:
    """SWAP incoming score below min_score threshold."""

    def test_incoming_below_min(self):
        ctx = _ctx(positions=[_position("WEAK")], cash=0, total=100000)
        # incoming score 50 < incoming_min_score 60
        rec_map = {
            "NVDA": _rec("NVDA", action="BUY", score=50),
            "WEAK": _rec("WEAK", action="HOLD", score=10),
        }
        state = _state(
            ticker_actions={"NVDA": {"action": "BUY", "scan_count": 3}},
            turnover={"swaps_today": 0, "swap_date": "", "trims_this_week": {}, "last_trade_dates": {}},
        )
        config = _config()

        result = _evaluate_swap(ctx, rec_map, state, config, "NVDA", rec_map["NVDA"])
        assert result is None


class TestCautionAggressiveTrimOnLowScore:
    """Very negative score (-50) doubles the trim fraction."""

    def test_aggressive_trim(self):
        pos = _position("BAD", current_price=100, shares=20)
        ctx = _ctx(positions=[pos])
        rec_map = {"BAD": _rec("BAD", action="CAUTION", score=-60)}
        state = _state(
            ticker_actions={"BAD": {"action": "CAUTION", "scan_count": 6, "eod_count": 1}},
        )
        config = _config()

        with patch(_P_SETTINGS_STRATEGIES, return_value=_strategies()):
            results = _evaluate_risk_actions(ctx, rec_map, state, config)

        trims = [s for s in results if s.suggestion_type == SuggestionType.TRIM_CAUTION]
        assert len(trims) == 1
        # score < -50, so trim_fraction doubles from 0.25 to 0.50
        assert trims[0].trim_fraction == pytest.approx(0.50)
        assert trims[0].suggested_amount == pytest.approx(1000.0)  # 2000 * 0.50


class TestWatchlistDisabled:
    """WATCHLIST starters disabled via config."""

    @patch(_P_SETTINGS_STRATEGIES)
    def test_disabled_returns_empty(self, mock_strat):
        mock_strat.return_value = _strategies()
        ctx = _ctx(cash=20000, total=100000)
        rec_map = {"ACME": _rec("ACME", action="WATCHLIST", score=55)}
        config = _config(allow_watchlist_starters=False)

        results = _evaluate_watchlist(ctx, rec_map, _state(), config)
        assert len(results) == 0


class TestBuyFromCashWithFreedCash:
    """Freed cash from trims adds to deployable amount."""

    @patch(_P_SETTINGS_STRATEGIES)
    @patch(_P_ALLOC_BUY_SIZE)
    @patch(_P_ALLOC_BUY_ELIGIBLE)
    def test_freed_cash_extends_deployable(self, mock_eligible, mock_size, mock_strat):
        mock_eligible.return_value = _risk_check(allowed=True)
        mock_size.return_value = 5000.0
        mock_strat.return_value = _strategies()

        # cash=10000, total=100000, reserve=12000
        # deployable = 10000 + 5000 (freed) - 12000 = 3000
        ctx = _ctx(cash=10000, total=100000)
        rec_map = {"NVDA": _rec("NVDA", action="BUY", score=70)}
        state = _state()
        config = _config()

        results = _evaluate_deployment(ctx, rec_map, state, config, freed_cash=5000)

        buys = [s for s in results if s.suggestion_type == SuggestionType.BUY_FROM_CASH]
        assert len(buys) == 1
        assert buys[0].suggested_amount == pytest.approx(3000.0)
