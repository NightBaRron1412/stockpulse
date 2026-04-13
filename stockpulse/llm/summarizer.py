"""LLM summarizer using AMD Claude API via Anthropic SDK."""
import logging
from stockpulse.config.settings import get_config
from stockpulse.llm.fallback import fallback_thesis, fallback_catalyst_summary

logger = logging.getLogger(__name__)
_client = None

def _get_client():
    global _client
    if _client is None:
        cfg = get_config()
        if not cfg["llm_enabled"]:
            return None
        try:
            import anthropic
            _client = anthropic.Anthropic(api_key=cfg["llm_api_key"], base_url=cfg["llm_base_url"])
        except Exception:
            logger.warning("Failed to initialize Anthropic client")
            return None
    return _client

def _call_llm(prompt: str, max_tokens: int = 300) -> str | None:
    client = _get_client()
    if client is None:
        return None
    cfg = get_config()
    try:
        response = client.messages.create(model=cfg["llm_model"], max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}])
        return response.content[0].text
    except Exception:
        logger.debug("LLM call failed, falling back to rules-based")
        return None

def generate_thesis(ticker: str, action: str, signals: dict, composite: float) -> str:
    signal_summary = "\n".join(f"- {name}: score={d['score']:.0f}, weight={d['weight']}"
        for name, d in signals.items())
    prompt = (f"You are a stock analyst. Generate a concise 2-sentence thesis for "
        f"a {action} recommendation on {ticker}.\n\nComposite score: {composite:.1f}\n"
        f"Signals:\n{signal_summary}\n\nBe specific about which signals drive the recommendation. "
        f"Do not use disclaimers.")
    result = _call_llm(prompt, max_tokens=150)
    if result:
        return result.strip()
    return fallback_thesis(action, signals, composite)

def generate_catalyst_narrative(ticker: str, signals: dict) -> str:
    prompt = (f"Summarize the catalyst picture for {ticker} in 1-2 sentences.\n\n"
        f"Earnings signal score: {signals.get('earnings', {}).get('score', 0)}\n"
        f"SEC filing signal score: {signals.get('sec_filing', {}).get('score', 0)}\n"
        f"News sentiment score: {signals.get('news_sentiment', {}).get('score', 0)}\n\n"
        f"Only mention catalysts that are present (non-zero scores). Be factual.")
    result = _call_llm(prompt, max_tokens=100)
    if result:
        return result.strip()
    return fallback_catalyst_summary(ticker, signals)

def summarize_filing(filing_text: str, ticker: str) -> str:
    prompt = (f"Summarize this SEC filing excerpt for {ticker} in 3 bullet points. "
        f"Focus on: revenue impact, risk factors, material events.\n\n{filing_text[:3000]}")
    result = _call_llm(prompt, max_tokens=200)
    return result.strip() if result else "Filing summary unavailable (LLM offline)"
