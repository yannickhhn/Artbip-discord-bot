"""
Config for the Art Telephone tracker bot.

Fill in TOKEN and CHANNEL_ID below (or set them as environment variables,
see README.md). Edit the keyword lists to match how your artists actually
type "started" / "finished" in each language.
"""

import os

from dotenv import load_dotenv

load_dotenv()

# --- Required settings -------------------------------------------------

# Your bot token from the Discord Developer Portal.
# Prefer setting this as an environment variable instead of hardcoding it.
TOKEN = os.environ.get("DISCORD_BOT_TOKEN", "")

# The IDs of the channels this bot should police (comma-separated in the
# env var, or edit the list directly below).
# Right-click each channel in Discord (Developer Mode must be on) -> Copy Channel ID
_channel_ids_env = os.environ.get("DISCORD_CHANNEL_IDS", "1528835863088468058,1528836936473510059,1528837215277420674,1529121037596364880")
CHANNEL_IDS = (
    [int(c.strip()) for c in _channel_ids_env.split(",") if c.strip()]
    if _channel_ids_env
    else []
)
# Or just list them here directly, e.g.:
# CHANNEL_IDS = [123456789012345678, 234567890123456789, 345678901234567890]

# Optional: a channel ID where the bot posts a log line every time it removes
# a message — who, what they said, and what action was taken (DM sent /
# channel fallback / neither). Leave blank/0 to disable channel logging
# (console logging via `logging` always still happens either way).
_log_channel_id_env = os.environ.get("DISCORD_LOG_CHANNEL_ID", "1532402854487265452").strip()
LOG_CHANNEL_ID = int(_log_channel_id_env) if _log_channel_id_env else None

# Your Anthropic API key, from https://console.anthropic.com/settings/keys
# Used to understand intent (e.g. "starting now" vs "starting tomorrow")
# for messages that aren't an exact keyword match.
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")

# Small, fast, cheap model — plenty for this classification task.
CLASSIFIER_MODEL = "claude-haiku-4-5-20251001"

# If True (default), messages that don't exactly match a keyword fall back to
# the Claude classifier for intent detection (see classifier.py) — e.g. this
# is what distinguishes "starting now" from "starting later".
# If False, no Claude API calls are made at all: a message is instead allowed
# if it simply CONTAINS a keyword anywhere. ANTHROPIC_API_KEY is not needed
# in that mode.
_use_classifier_env = os.environ.get("USE_CLASSIFIER", "false")
USE_CLASSIFIER = _use_classifier_env.strip().lower() not in ("false", "0", "no")

# --- Keywords (fast path) -------------------------------------------------
# If a message, once mentions/emojis/punctuation are stripped, EXACTLY
# matches one of these, it's allowed instantly with no API call — this
# covers the common case (someone just types "started" / "vita" / etc.)
# and keeps things fast/free. Anything that doesn't match exactly falls
# through to the Claude classifier (see classifier.py), which is what
# understands things like "commence maintenant" vs "commence demain".
# Matching is case-insensitive and ignores accents (é vs e).

START_KEYWORDS = [
    # English
    "start", "started", "starting",
    # French
    "commence", "je commence", "début", "debut", "commencé", "commence a dessiner","vient de commencer","Je commence maintenant", "maintenant", 
    # Malagasy (please double check these with a native speaker -
    # "manomboka" = to start/begin)
    "manomboka", "manomboka aho","tour","lesgo","let's go","let's gooo","I'm on it","c'est parti",
]

FINISH_KEYWORDS = [
    # English
    "done", "finish", "finished", "complete", "completed",
    # French
    "fini", "terminé", "termine", "j'ai fini", "j'ai terminé","finii","finiii",
    # Malagasy (please double check these -
    # "vita" = done/finished)
    "vita", "efa vita", "your turn","turn","à toi", "tuurn",
]

# --- Forbidden words (always block) -----------------------------------------
# If a message contains any of these anywhere, it's blocked outright — before
# the fast path, before the classifier, in every mode. These flag messages
# that are about the future/later rather than a right-now announcement, e.g.
# "je commence demain" would otherwise slip through the USE_CLASSIFIER=false
# contains-check just because it contains "commence".
FORBIDDEN_KEYWORDS = [
    # English
    "tomorrow", "later",
    # French
    "demain", "plus tard",
    # Malagasy (please double check these with a native speaker -
    # "rahampitso" = tomorrow)
    "rahampitso", "dans", "vers","afternoon","soir",
]

# --- Behavior --------------------------------------------------------------

# If True, a non-matching message also gets a short reminder posted in the
# channel (auto-deleted after REMINDER_DELETE_AFTER seconds) as a fallback
# for users who have server DMs disabled.
CHANNEL_FALLBACK_REMINDER = True
REMINDER_DELETE_AFTER = 8  # seconds

# How many of the most recent messages to check in each watched channel when
# the bot (re)connects — catches anything posted while it was offline that
# wouldn't have been moderated in real time. Set to 0 to disable.
CATCHUP_MESSAGE_LIMIT = 5

DM_MESSAGE = (
    "Salut ! Ton message dans le salon izazao a été supprimé.\n\n"
    "Ce salon sert uniquement à dire que tu as **commencé** ou **fini** "
    "ton dessin (en anglais, français ou malgache) — pas d'autre discussion, merci. \n\n" \
    "Si tu veux discuter, utilise #chatting.\n\n"  \
    "" \
    "Je suis encore en phase de test, préviens Yannick si j'ai supprimé ton message par erreur :'))"
)
  