"""Tests for LLM integration — summarizer, news analyzer, filing analyzer."""
from unittest.mock import patch, MagicMock


# ─────────────────────────────────────────────
# summarizer._call_llm
# ─────────────────────────────────────────────

def test_call_llm_returns_none_when_disabled():
    from stockpulse.llm.summarizer import _call_llm
    with patch("stockpulse.llm.summarizer._get_client", return_value=None):
        result = _call_llm("test prompt")
        assert result is None


def test_call_llm_returns_text_on_success():
    from stockpulse.llm.summarizer import _call_llm
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Hello world")]
    mock_client.messages.create.return_value = mock_response

    with patch("stockpulse.llm.summarizer._get_client", return_value=mock_client), \
         patch("stockpulse.llm.summarizer.get_config", return_value={"llm_model": "test-model"}):
        result = _call_llm("test prompt")
        assert result == "Hello world"


def test_call_llm_model_override():
    from stockpulse.llm.summarizer import _call_llm
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="Hello")]
    mock_client.messages.create.return_value = mock_response

    with patch("stockpulse.llm.summarizer._get_client", return_value=mock_client), \
         patch("stockpulse.llm.summarizer.get_config", return_value={"llm_model": "default-model"}):
        _call_llm("test", model="opus-override")
        mock_client.messages.create.assert_called_once()
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "opus-override"


def test_call_llm_falls_back_on_error():
    from stockpulse.llm.summarizer import _call_llm
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("API error")

    with patch("stockpulse.llm.summarizer._get_client", return_value=mock_client), \
         patch("stockpulse.llm.summarizer.get_config", return_value={"llm_model": "test"}):
        result = _call_llm("test")
        assert result is None


def test_call_llm_uses_default_model_when_no_override():
    """Without model= kwarg, the model from get_config should be used."""
    from stockpulse.llm.summarizer import _call_llm
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="ok")]
    mock_client.messages.create.return_value = mock_response

    with patch("stockpulse.llm.summarizer._get_client", return_value=mock_client), \
         patch("stockpulse.llm.summarizer.get_config", return_value={"llm_model": "sonnet-123"}):
        _call_llm("hello")
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["model"] == "sonnet-123"


def test_call_llm_passes_correct_max_tokens():
    from stockpulse.llm.summarizer import _call_llm
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text="ok")]
    mock_client.messages.create.return_value = mock_response

    with patch("stockpulse.llm.summarizer._get_client", return_value=mock_client), \
         patch("stockpulse.llm.summarizer.get_config", return_value={"llm_model": "test"}):
        _call_llm("prompt", max_tokens=42)
        call_kwargs = mock_client.messages.create.call_args
        assert call_kwargs.kwargs["max_tokens"] == 42


# ─────────────────────────────────────────────
# news_analyzer
# ─────────────────────────────────────────────

def test_news_analyzer_fallback():
    from stockpulse.llm.news_analyzer import analyze_news_sentiment
    with patch("stockpulse.llm.news_analyzer.get_news", return_value=[{"title": "Stock surges on earnings beat"}]), \
         patch("stockpulse.llm.news_analyzer._get_llm_client", return_value=None):
        result = analyze_news_sentiment("TEST")
        assert result["source"] == "fallback"
        assert result["score"] > 0  # "surges" and "beat" are positive keywords


def test_news_analyzer_no_news():
    from stockpulse.llm.news_analyzer import analyze_news_sentiment
    with patch("stockpulse.llm.news_analyzer.get_news", return_value=[]):
        result = analyze_news_sentiment("TEST")
        assert result["source"] == "none"
        assert result["score"] == 0


def test_news_analyzer_negative_keywords():
    """Headlines with negative keywords should produce a negative score."""
    from stockpulse.llm.news_analyzer import analyze_news_sentiment
    with patch("stockpulse.llm.news_analyzer.get_news", return_value=[
                   {"title": "Stock drops on earnings miss"},
                   {"title": "CEO resigned amid fraud investigation"},
               ]), \
         patch("stockpulse.llm.news_analyzer._get_llm_client", return_value=None):
        result = analyze_news_sentiment("TEST")
        assert result["source"] == "fallback"
        assert result["score"] < 0


def test_news_analyzer_neutral_keywords():
    """Headlines with no positive/negative keywords should produce 0 score."""
    from stockpulse.llm.news_analyzer import analyze_news_sentiment
    with patch("stockpulse.llm.news_analyzer.get_news", return_value=[{"title": "Company files annual report"}]), \
         patch("stockpulse.llm.news_analyzer._get_llm_client", return_value=None):
        result = analyze_news_sentiment("TEST")
        # No positive or negative keywords — score should be 0
        assert result["score"] == 0.0


def test_news_analyzer_llm_path():
    """When LLM client is available, _llm_analyze result should flow through."""
    from stockpulse.llm.news_analyzer import analyze_news_sentiment
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"events": [], "overall_score": 25, "summary": "Positive quarter"}')]
    mock_client.messages.create.return_value = mock_response

    with patch("stockpulse.llm.news_analyzer.get_news", return_value=[{"title": "Beats estimates"}]), \
         patch("stockpulse.llm.news_analyzer._get_llm_client", return_value=mock_client), \
         patch("stockpulse.llm.news_analyzer.get_config", return_value={"llm_model": "test"}):
        result = analyze_news_sentiment("TEST")
        assert result["source"] == "llm"
        assert result["score"] == 25.0


# ─────────────────────────────────────────────
# filing_analyzer
# ─────────────────────────────────────────────

def test_filing_analyzer_fallback_negative():
    from stockpulse.llm.filing_analyzer import analyze_filing_direction
    # _get_client is imported lazily from stockpulse.llm.summarizer inside the function
    with patch("stockpulse.llm.summarizer._get_client", return_value=None):
        result = analyze_filing_direction("TEST", "8-K", ["4.02"], "restatement of financials")
        assert result["direction"] == "bearish"
        assert result["source"] == "fallback"


def test_filing_analyzer_fallback_neutral():
    from stockpulse.llm.filing_analyzer import analyze_filing_direction
    with patch("stockpulse.llm.summarizer._get_client", return_value=None):
        result = analyze_filing_direction("TEST", "8-K", ["8.01"], "other events")
        assert result["direction"] == "neutral"
        assert result["source"] == "fallback"


def test_filing_analyzer_fallback_bullish_keyword():
    """Description containing 'acquisition' should yield bullish fallback."""
    from stockpulse.llm.filing_analyzer import analyze_filing_direction
    with patch("stockpulse.llm.summarizer._get_client", return_value=None):
        result = analyze_filing_direction("TEST", "8-K", ["8.01"], "new acquisition agreement signed")
        assert result["direction"] == "bullish"
        assert result["source"] == "fallback"


def test_filing_analyzer_fallback_bearish_keyword():
    """Description containing 'bankruptcy' should yield bearish fallback."""
    from stockpulse.llm.filing_analyzer import analyze_filing_direction
    with patch("stockpulse.llm.summarizer._get_client", return_value=None):
        result = analyze_filing_direction("TEST", "8-K", ["8.01"], "company files for bankruptcy")
        assert result["direction"] == "bearish"
        assert result["source"] == "fallback"


def test_filing_analyzer_llm_path():
    """When LLM returns valid JSON, result should use llm source."""
    from stockpulse.llm.filing_analyzer import analyze_filing_direction
    mock_client = MagicMock()
    mock_response = MagicMock()
    mock_response.content = [MagicMock(text='{"direction": "bullish", "confidence": 0.8, "reasoning": "revenue guidance raised"}')]
    mock_client.messages.create.return_value = mock_response

    # _get_client is resolved by importing from stockpulse.llm.summarizer at call time;
    # get_config is a module-level import in filing_analyzer so patch via its module.
    with patch("stockpulse.llm.summarizer._get_client", return_value=mock_client), \
         patch("stockpulse.llm.filing_analyzer.get_config", return_value={"llm_model": "test"}):
        result = analyze_filing_direction("AAPL", "8-K", ["2.02"], "earnings results")
        assert result["source"] == "llm"
        assert result["direction"] == "bullish"
        assert result["confidence"] == 0.8


def test_filing_analyzer_llm_error_falls_to_fallback():
    """When LLM raises an exception, should fall back gracefully."""
    from stockpulse.llm.filing_analyzer import analyze_filing_direction
    mock_client = MagicMock()
    mock_client.messages.create.side_effect = Exception("network error")

    with patch("stockpulse.llm.summarizer._get_client", return_value=mock_client), \
         patch("stockpulse.llm.filing_analyzer.get_config", return_value={"llm_model": "test"}):
        result = analyze_filing_direction("AAPL", "8-K", ["8.01"], "routine filing")
        assert result["source"] == "fallback"
