"""Fundamental/catalyst signal generators. Each function returns a score from -100 to +100."""
import logging
from stockpulse.data.provider import get_earnings_dates, get_news
from stockpulse.sec.filings import get_recent_filings
from stockpulse.sec.insider import get_insider_transactions
from stockpulse.config.settings import load_strategies

logger = logging.getLogger(__name__)

_POSITIVE_KEYWORDS = [
    "beat", "surge", "jump", "soar", "upgrade", "strong", "growth",
    "profit", "record", "exceeded", "outperform", "buy", "bullish",
    "positive", "gain", "rally", "breakout", "momentum", "dividend",
    "innovation", "partnership", "expansion", "approval",
]
_NEGATIVE_KEYWORDS = [
    "miss", "decline", "drop", "fall", "downgrade", "weak", "loss",
    "layoff", "cut", "warning", "concern", "risk", "sell", "bearish",
    "negative", "crash", "lawsuit", "investigation", "recall", "debt",
    "bankruptcy", "fraud", "resign", "delay",
]

def _clamp(value: float, lo: float = -100.0, hi: float = 100.0) -> float:
    return max(lo, min(hi, value))

def calc_earnings_signal(ticker: str) -> float:
    cfg = load_strategies().get("signals", {}).get("earnings", {})
    proximity_days = cfg.get("proximity_days", 14)
    try:
        dates = get_earnings_dates(ticker)
    except ValueError:
        return 0.0
    if not dates:
        return 0.0
    for d in dates:
        days_away = d.get("days_away", 999)
        if 0 <= days_away <= proximity_days:
            intensity = 1.0 - (days_away / proximity_days)
            return _clamp(intensity * 40)
    return 0.0

def calc_sec_filing_signal(ticker: str) -> float:
    cfg = load_strategies().get("signals", {}).get("sec_filing", {})
    lookback_days = cfg.get("lookback_days", 30)
    score = 0.0
    filings = get_recent_filings(ticker, lookback_days)
    for filing in filings:
        form = filing.get("form", "")
        if form == "8-K":
            score += 15
        elif form in ("10-K", "10-Q"):
            score += 5
    insiders = get_insider_transactions(ticker, lookback_days)
    if insiders:
        score += min(len(insiders) * 5, 20)
    return _clamp(score)

def calc_news_sentiment_signal(ticker: str) -> float:
    try:
        news = get_news(ticker)
    except ValueError:
        return 0.0
    if not news:
        return 0.0
    positive_count = 0
    negative_count = 0
    for item in news:
        title = item.get("title", "").lower()
        for kw in _POSITIVE_KEYWORDS:
            if kw in title:
                positive_count += 1
        for kw in _NEGATIVE_KEYWORDS:
            if kw in title:
                negative_count += 1
    if positive_count + negative_count == 0:
        return 0.0
    net = positive_count - negative_count
    total = positive_count + negative_count
    ratio = net / total
    return _clamp(ratio * 60)
