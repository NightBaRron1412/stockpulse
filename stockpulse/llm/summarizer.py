"""LLM summarizer using Claude API via Anthropic SDK."""
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
            import os
            # Support custom auth headers (e.g. Ocp-Apim-Subscription-Key)
            custom_headers = {}
            raw_headers = os.getenv("ANTHROPIC_CUSTOM_HEADERS", "")
            for line in raw_headers.strip().splitlines():
                if ":" in line:
                    key, val = line.split(":", 1)
                    custom_headers[key.strip()] = val.strip()
            _client = anthropic.Anthropic(
                api_key=cfg["llm_api_key"],
                base_url=cfg["llm_base_url"],
                default_headers=custom_headers,
            )
            logger.info("LLM client initialized: base_url=%s, model=%s, custom_headers=%s",
                        cfg["llm_base_url"], cfg["llm_model"], bool(custom_headers))
        except Exception as e:
            logger.error("Failed to initialize Anthropic client: %s", str(e)[:100])
            return None
    return _client

def _call_llm(prompt: str, max_tokens: int = 300, model: str | None = None) -> str | None:
    client = _get_client()
    if client is None:
        logger.warning("LLM client not initialized — using fallback")
        return None
    cfg = get_config()
    use_model = model or cfg["llm_model"]
    try:
        logger.info("LLM call: model=%s, prompt_len=%d", use_model, len(prompt))
        response = client.messages.create(model=use_model, max_tokens=max_tokens,
            messages=[{"role": "user", "content": prompt}])
        result = response.content[0].text
        logger.info("LLM success: model=%s, response_len=%d", use_model, len(result))
        return result
    except Exception as e:
        logger.warning("LLM call failed (model=%s): %s — using fallback", use_model, str(e)[:100])
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
