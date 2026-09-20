"""Chart screenshot analysis with Claude vision."""
import base64
import logging

import anthropic

from data.config import ANTHROPIC_API_KEY

MODEL = "claude-opus-5"
LANGUAGE_NAMES = {"uz": "Uzbek (Latin script)", "en": "English"}

SYSTEM = """You are a technical analyst specialising in crude oil (WTI and Brent, CFDs and futures), \
helping a retail trader who sends chart screenshots from TradingView or a broker terminal.

Read the chart carefully: instrument and timeframe (from the header if visible), trend structure \
and recent swings, key support/resistance zones, and anything drawn on it (order blocks, trendlines, \
moving averages, RSI, volume and so on). Then give your read:
- Bias: bullish, bearish or neutral, and why.
- A trade idea if the chart supports one: entry zone, stop-loss, take-profit using levels actually \
visible on the chart, and the approximate risk/reward.
- What would invalidate the idea.

Only use prices you can read from the chart. If something is unreadable, or the image is not a price \
chart, say so. Be direct about uncertainty.

Format for Telegram: plain text, short sections each starting with an emoji, no Markdown \
(no **, #, or backticks). Keep it under roughly 250 words. Finish with one line noting this is \
analysis, not financial advice."""

_client = None


def enabled() -> bool:
    return bool(ANTHROPIC_API_KEY)


def _get_client() -> anthropic.AsyncAnthropic:
    global _client
    if _client is None:
        _client = anthropic.AsyncAnthropic(api_key=ANTHROPIC_API_KEY)
    return _client


async def analyze_chart(image: bytes, media_type: str, lang: str, question: str | None = None) -> str | None:
    """Returns the analysis text, or None if the model declined to answer."""
    prompt = f"Analyse this chart. Reply in {LANGUAGE_NAMES.get(lang, 'English')}."
    if question:
        prompt += f"\n\nThe trader's question: {question}"
    response = await _get_client().beta.messages.create(
        model=MODEL,
        max_tokens=4000,
        system=SYSTEM,
        # If the primary model declines, the API retries on a fallback model in the same call
        betas=["server-side-fallback-2026-07-01"],
        fallbacks="default",
        messages=[{"role": "user", "content": [
            {"type": "image", "source": {"type": "base64", "media_type": media_type,
                                         "data": base64.standard_b64encode(image).decode()}},
            {"type": "text", "text": prompt},
        ]}],
    )
    if response.stop_reason == "refusal":
        logging.warning(f"Chart analysis refused: {response.stop_details}")
        return None
    return "".join(block.text for block in response.content if block.type == "text").strip()
