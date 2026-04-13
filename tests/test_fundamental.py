from stockpulse.signals.fundamental import (
    calc_earnings_signal, calc_sec_filing_signal, calc_news_sentiment_signal,
)

def test_earnings_signal_returns_bounded_score():
    score = calc_earnings_signal("AAPL")
    assert -100 <= score <= 100

def test_sec_filing_signal_returns_bounded_score():
    score = calc_sec_filing_signal("AAPL")
    assert -100 <= score <= 100

def test_news_sentiment_signal_returns_bounded_score():
    score = calc_news_sentiment_signal("AAPL")
    assert -100 <= score <= 100
