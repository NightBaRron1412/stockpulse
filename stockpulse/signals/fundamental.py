"""Fundamental/catalyst signal generators. Each function returns a score from -100 to +100."""
import logging
from stockpulse.data.provider import get_earnings_dates, get_news
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
    """Earnings proximity as a RISK flag, not bullish signal.
    Per recommended: earnings proximity = 0 as directional signal.
    Returns negative score within blackout window to warn."""
    cfg = load_strategies().get("signals", {}).get("earnings", {})
    blackout_days = cfg.get("blackout_days", 3)

    try:
        dates = get_earnings_dates(ticker)
    except ValueError:
        return 0.0
    if not dates:
        return 0.0

    for d in dates:
        days_away = d.get("days_away", 999)
        if 0 <= days_away <= blackout_days:
            return -30.0  # inside blackout = risk flag (penalize)
        elif days_away < 0 and days_away >= -5:
            return 0.0    # just reported -- neutral, let other signals judge

    return 0.0

def calc_sec_filing_signal(ticker: str) -> float:
    """SEC filing catalyst signal using the 8-K classification + insider scoring."""
    cfg = load_strategies().get("signals", {}).get("sec_filing", {})
    lookback_days = cfg.get("lookback_days", 30)
    insider_buy_weight = cfg.get("insider_buy_weight", 3)

    # Filing importance score (8-K event classification)
    from stockpulse.sec.filings import score_filings
    filing_score = score_filings(ticker, lookback_days)

    # Insider buy score (role-weighted, cluster-multiplied)
    from stockpulse.sec.insider import score_insider_activity
    insider_score = score_insider_activity(ticker, lookback_days)

    # Combine: filing events + insider buying (insider weighted per config)
    combined = (filing_score + insider_score * (insider_buy_weight / 3.0)) / 2.0

    return _clamp(combined)

def calc_news_sentiment_signal(ticker: str, use_llm: bool = True) -> float:
    """News sentiment signal.

    Args:
        use_llm: If True, use LLM analysis. If False, use fast keyword fallback.
                 Set to False for full S&P 500 scans to keep scan under 30 min.
    """
    try:
        from stockpulse.llm.news_analyzer import analyze_news_sentiment, _fallback_analyze
        from stockpulse.data.provider import get_news
        if not use_llm:
            news = get_news(ticker)
            if not news:
                return 0.0
            headlines = [n.get("title", "") for n in news if n.get("title")]
            if not headlines:
                return 0.0
            result = _fallback_analyze(ticker, headlines)
            return max(-100.0, min(100.0, result["score"]))
        result = analyze_news_sentiment(ticker)
        return max(-100.0, min(100.0, result["score"]))
    except ValueError:
        return 0.0
    except Exception:
        logger.debug("News sentiment failed for %s", ticker)
        return 0.0
