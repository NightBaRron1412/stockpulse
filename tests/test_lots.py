"""Tests for stockpulse.portfolio.lots — tax lot tracking."""
from datetime import datetime, timedelta
from unittest.mock import patch, MagicMock

from stockpulse.portfolio.lots import (
    ensure_lots,
    get_lots,
    add_lot,
    compute_lot_tax_info,
    select_lots_fifo,
    compute_tax_impact,
    check_wash_sale,
)


# ── ensure_lots ────────────────────────────────────────────────────

def test_ensure_lots_migrates_position_without_lots():
    """Position without 'lots' key gets a single lot from entry fields."""
    portfolio = {
        "positions": [
            {"ticker": "AAPL", "shares": 10, "entry_price": 150.0, "entry_date": "2024-06-01"},
        ]
    }
    with patch("stockpulse.portfolio.lots._save_portfolio"):
        result = ensure_lots(portfolio)

    pos = result["positions"][0]
    assert "lots" in pos
    assert len(pos["lots"]) == 1
    lot = pos["lots"][0]
    assert lot["shares"] == 10
    assert lot["cost_basis"] == 150.0
    assert lot["acquired_at"] == "2024-06-01"
    assert lot["source"] == "migration"
    assert "lot_id" in lot


def test_ensure_lots_leaves_existing_lots_untouched():
    """Position that already has lots is not modified."""
    existing_lot = {"lot_id": "abc", "shares": 5, "cost_basis": 100.0,
                    "acquired_at": "2024-01-01", "source": "manual"}
    portfolio = {
        "positions": [
            {"ticker": "MSFT", "shares": 5, "lots": [existing_lot]},
        ]
    }
    with patch("stockpulse.portfolio.lots._save_portfolio") as mock_save:
        result = ensure_lots(portfolio)

    # Should not save because nothing changed
    mock_save.assert_not_called()
    assert result["positions"][0]["lots"] == [existing_lot]


def test_ensure_lots_handles_empty_positions():
    portfolio = {"positions": []}
    with patch("stockpulse.portfolio.lots._save_portfolio") as mock_save:
        result = ensure_lots(portfolio)
    mock_save.assert_not_called()
    assert result["positions"] == []


# ── get_lots ───────────────────────────────────────────────────────

def test_get_lots_returns_sorted_fifo():
    """Lots are returned sorted by acquired_at date, oldest first."""
    portfolio = {
        "positions": [{
            "ticker": "AAPL",
            "lots": [
                {"lot_id": "new", "shares": 5, "cost_basis": 200.0, "acquired_at": "2025-01-15"},
                {"lot_id": "old", "shares": 3, "cost_basis": 150.0, "acquired_at": "2024-03-01"},
                {"lot_id": "mid", "shares": 7, "cost_basis": 180.0, "acquired_at": "2024-09-10"},
            ],
        }]
    }
    lots = get_lots("AAPL", portfolio)
    assert [l["lot_id"] for l in lots] == ["old", "mid", "new"]


def test_get_lots_returns_empty_for_unknown_ticker():
    portfolio = {"positions": [{"ticker": "MSFT", "lots": []}]}
    lots = get_lots("AAPL", portfolio)
    assert lots == []


def test_get_lots_returns_empty_for_no_positions():
    portfolio = {"positions": []}
    lots = get_lots("AAPL", portfolio)
    assert lots == []


# ── add_lot ────────────────────────────────────────────────────────

def test_add_lot_appends_to_existing_position():
    portfolio = {
        "positions": [{
            "ticker": "AAPL",
            "shares": 10,
            "lots": [
                {"lot_id": "first", "shares": 10, "cost_basis": 150.0,
                 "acquired_at": "2024-01-01"},
            ],
        }]
    }
    with patch("stockpulse.portfolio.lots._load_portfolio", return_value=portfolio), \
         patch("stockpulse.portfolio.lots._save_portfolio"):
        lot = add_lot("AAPL", 5, 200.0, "2025-03-01")

    assert lot["shares"] == 5
    assert lot["cost_basis"] == 200.0
    assert lot["acquired_at"] == "2025-03-01"
    assert lot["source"] == "manual"
    # Aggregate shares updated
    assert portfolio["positions"][0]["shares"] == 15
    assert len(portfolio["positions"][0]["lots"]) == 2


def test_add_lot_creates_new_position_if_not_found():
    portfolio = {"positions": []}
    with patch("stockpulse.portfolio.lots._load_portfolio", return_value=portfolio), \
         patch("stockpulse.portfolio.lots._save_portfolio"):
        lot = add_lot("NVDA", 20, 800.0, "2025-02-01")

    assert lot["shares"] == 20
    assert lot["cost_basis"] == 800.0
    assert len(portfolio["positions"]) == 1
    new_pos = portfolio["positions"][0]
    assert new_pos["ticker"] == "NVDA"
    assert new_pos["shares"] == 20
    assert new_pos["entry_price"] == 800.0
    assert len(new_pos["lots"]) == 1


# ── compute_lot_tax_info ──────────────────────────────────────────

def test_compute_lot_tax_info_short_term_gain():
    """Lot held < 365 days with gain."""
    recent_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
    lot = {"lot_id": "st", "shares": 10, "cost_basis": 100.0, "acquired_at": recent_date}
    info = compute_lot_tax_info(lot, current_price=120.0)

    assert info["is_long_term"] is False
    assert info["term"] == "short-term"
    assert info["gain_per_share"] == 20.0
    assert info["total_gain"] == 200.0
    assert info["holding_days"] < 365


def test_compute_lot_tax_info_long_term_gain():
    """Lot held >= 365 days with gain."""
    old_date = (datetime.now() - timedelta(days=400)).strftime("%Y-%m-%d")
    lot = {"lot_id": "lt", "shares": 5, "cost_basis": 50.0, "acquired_at": old_date}
    info = compute_lot_tax_info(lot, current_price=80.0)

    assert info["is_long_term"] is True
    assert info["term"] == "long-term"
    assert info["gain_per_share"] == 30.0
    assert info["total_gain"] == 150.0
    assert info["holding_days"] >= 365


def test_compute_lot_tax_info_loss():
    """Lot with a loss (current_price < cost_basis)."""
    recent_date = (datetime.now() - timedelta(days=50)).strftime("%Y-%m-%d")
    lot = {"lot_id": "loss", "shares": 10, "cost_basis": 200.0, "acquired_at": recent_date}
    info = compute_lot_tax_info(lot, current_price=180.0)

    assert info["gain_per_share"] == -20.0
    assert info["total_gain"] == -200.0
    assert info["term"] == "short-term"


def test_compute_lot_tax_info_boundary_365_days():
    """Exactly 365 days should be long-term."""
    boundary_date = (datetime.now() - timedelta(days=365)).strftime("%Y-%m-%d")
    lot = {"lot_id": "boundary", "shares": 1, "cost_basis": 100.0, "acquired_at": boundary_date}
    info = compute_lot_tax_info(lot, current_price=110.0)

    assert info["is_long_term"] is True
    assert info["term"] == "long-term"


# ── select_lots_fifo ──────────────────────────────────────────────

def test_select_lots_fifo_selects_oldest_first():
    portfolio = {
        "positions": [{
            "ticker": "AAPL",
            "lots": [
                {"lot_id": "new", "shares": 10, "cost_basis": 200.0, "acquired_at": "2025-01-01"},
                {"lot_id": "old", "shares": 5, "cost_basis": 100.0, "acquired_at": "2023-06-01"},
            ],
        }]
    }
    selected = select_lots_fifo("AAPL", 5, portfolio)
    assert len(selected) == 1
    assert selected[0]["lot_id"] == "old"
    assert selected[0]["shares_to_sell"] == 5


def test_select_lots_fifo_partial_lot():
    """When selling fewer shares than the oldest lot holds."""
    portfolio = {
        "positions": [{
            "ticker": "AAPL",
            "lots": [
                {"lot_id": "big", "shares": 20, "cost_basis": 100.0, "acquired_at": "2023-01-01"},
            ],
        }]
    }
    selected = select_lots_fifo("AAPL", 7, portfolio)
    assert len(selected) == 1
    assert selected[0]["shares_to_sell"] == 7
    assert selected[0]["lot_id"] == "big"


def test_select_lots_fifo_spans_multiple_lots():
    """Selling more than the oldest lot requires spanning into the next."""
    portfolio = {
        "positions": [{
            "ticker": "AAPL",
            "lots": [
                {"lot_id": "first", "shares": 3, "cost_basis": 100.0, "acquired_at": "2023-01-01"},
                {"lot_id": "second", "shares": 10, "cost_basis": 150.0, "acquired_at": "2024-01-01"},
            ],
        }]
    }
    selected = select_lots_fifo("AAPL", 8, portfolio)
    assert len(selected) == 2
    assert selected[0]["lot_id"] == "first"
    assert selected[0]["shares_to_sell"] == 3
    assert selected[1]["lot_id"] == "second"
    assert selected[1]["shares_to_sell"] == 5


def test_select_lots_fifo_returns_empty_for_unknown_ticker():
    portfolio = {"positions": []}
    selected = select_lots_fifo("AAPL", 10, portfolio)
    assert selected == []


# ── compute_tax_impact ────────────────────────────────────────────

def test_compute_tax_impact_splits_short_and_long_term():
    """Mix of short-term and long-term lots correctly split."""
    short_date = (datetime.now() - timedelta(days=100)).strftime("%Y-%m-%d")
    long_date = (datetime.now() - timedelta(days=500)).strftime("%Y-%m-%d")
    portfolio = {
        "positions": [{
            "ticker": "TEST",
            "lots": [
                {"lot_id": "long", "shares": 10, "cost_basis": 100.0, "acquired_at": long_date},
                {"lot_id": "short", "shares": 10, "cost_basis": 150.0, "acquired_at": short_date},
            ],
        }]
    }
    # Selling 15 shares at $200: 10 from long lot, 5 from short lot
    result = compute_tax_impact("TEST", 15, 200.0, portfolio)

    assert result["long_term_gain"] == 1000.0   # (200-100)*10
    assert result["short_term_gain"] == 250.0   # (200-150)*5
    assert result["total_gain"] == 1250.0
    assert len(result["lots_detail"]) == 2
    assert result["lots_detail"][0]["term"] == "long-term"
    assert result["lots_detail"][1]["term"] == "short-term"


def test_compute_tax_impact_all_short_term():
    short_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    portfolio = {
        "positions": [{
            "ticker": "X",
            "lots": [
                {"lot_id": "a", "shares": 10, "cost_basis": 50.0, "acquired_at": short_date},
            ],
        }]
    }
    result = compute_tax_impact("X", 10, 60.0, portfolio)
    assert result["short_term_gain"] == 100.0
    assert result["long_term_gain"] == 0.0
    assert result["total_gain"] == 100.0


def test_compute_tax_impact_loss():
    short_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    portfolio = {
        "positions": [{
            "ticker": "X",
            "lots": [
                {"lot_id": "a", "shares": 5, "cost_basis": 100.0, "acquired_at": short_date},
            ],
        }]
    }
    result = compute_tax_impact("X", 5, 80.0, portfolio)
    assert result["total_gain"] == -100.0
    assert result["short_term_gain"] == -100.0


# ── check_wash_sale ───────────────────────────────────────────────

def test_check_wash_sale_detects_recent_loss():
    """Sale at a loss within 30 days triggers wash sale."""
    recent_date = (datetime.now() - timedelta(days=10)).strftime("%Y-%m-%d")
    history = [
        {"ticker": "AAPL", "sold_at": recent_date, "gain": -500.0, "lot_id": "xyz"},
    ]
    result = check_wash_sale("AAPL", sold_lots_history=history)
    assert result["wash_sale"] is True
    assert result["loss"] == -500.0
    assert result["lot_id"] == "xyz"


def test_check_wash_sale_ignores_profit():
    """Sale at a profit does not trigger wash sale."""
    recent_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    history = [
        {"ticker": "AAPL", "sold_at": recent_date, "gain": 200.0, "lot_id": "abc"},
    ]
    result = check_wash_sale("AAPL", sold_lots_history=history)
    assert result["wash_sale"] is False


def test_check_wash_sale_ignores_old_loss():
    """Sale at a loss more than 30 days ago does not trigger wash sale."""
    old_date = (datetime.now() - timedelta(days=60)).strftime("%Y-%m-%d")
    history = [
        {"ticker": "AAPL", "sold_at": old_date, "gain": -300.0, "lot_id": "old"},
    ]
    result = check_wash_sale("AAPL", sold_lots_history=history)
    assert result["wash_sale"] is False


def test_check_wash_sale_ignores_different_ticker():
    """Loss on a different ticker does not trigger wash sale."""
    recent_date = (datetime.now() - timedelta(days=5)).strftime("%Y-%m-%d")
    history = [
        {"ticker": "MSFT", "sold_at": recent_date, "gain": -100.0, "lot_id": "msft1"},
    ]
    result = check_wash_sale("AAPL", sold_lots_history=history)
    assert result["wash_sale"] is False


def test_check_wash_sale_empty_history():
    result = check_wash_sale("AAPL", sold_lots_history=[])
    assert result["wash_sale"] is False


def test_check_wash_sale_boundary_30_days():
    """Sale at exactly 30 days ago with a loss should still trigger."""
    boundary_date = (datetime.now() - timedelta(days=30)).strftime("%Y-%m-%d")
    history = [
        {"ticker": "AAPL", "sold_at": boundary_date, "gain": -50.0, "lot_id": "edge"},
    ]
    result = check_wash_sale("AAPL", sold_lots_history=history)
    assert result["wash_sale"] is True
