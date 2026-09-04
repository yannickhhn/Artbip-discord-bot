"""
Classifies a message as START / FINISH / OTHER using the Claude API.

Only called for messages that didn't already exactly match a fast-path
keyword in config.py — e.g. "Je vais commencer maintenant" or "starting
this now!" should be understood as START, while "Je vais commencer
demain" or "I'll start tomorrow" should be OTHER (blocked), even though
they share a keyword.
"""

import logging

from anthropic import AsyncAnthropic

import config

log = logging.getLogger("telephone-bot.classifier")

_client = AsyncAnthropic(api_key=config.ANTHROPIC_API_KEY) if config.ANTHROPIC_API_KEY else None

SYSTEM_PROMPT = """\
You moderate ONE Discord channel used only for artists in a collaborative \
round-robin drawing game (like a game of telephone) to announce, in the \
moment, that they are starting or finishing their turn on a drawing. \
Messages may be written in English, French, or Malagasy, in any casual \
phrasing or spelling.

Classify the message as exactly one of:
START  - the author is announcing that they are beginning their drawing right now
FINISH - the author is announcing that they have just completed their drawing right now
OTHER  - anything else: small talk, questions, plans for later/tomorrow/future, \
past unrelated events, reactions, or anything not a present-tense start/finish announcement

Respond with exactly one word: START, FINISH, or OTHER. Nothing else."""


async def classify(content: str) -> str:
    """Returns "START", "FINISH", or "OTHER".

    Fails safe: if there's no API key configured or the API call errors
    out for any reason, returns "OTHER" so the message gets blocked
    rather than silently let through.
    """
    if _client is None:
        log.error("ANTHROPIC_API_KEY not configured — blocking by default.")
        return "OTHER"

    if not content.strip():
        return "OTHER"

    try:
        response = await _client.messages.create(
            model=config.CLASSIFIER_MODEL,
            max_tokens=5,
            system=SYSTEM_PROMPT,
            messages=[{"role": "user", "content": content}],
        )
        text = "".join(
            block.text for block in response.content if block.type == "text"
        ).strip().upper()

        if text.startswith("START"):
            return "START"
        if text.startswith("FINISH"):
            return "FINISH"
        return "OTHER"
    except Exception:
        log.exception("Classifier call failed — blocking message by default.")
        return "OTHER"
