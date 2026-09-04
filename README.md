# Art Telephone Tracker Bot

Watches one or more channels and deletes any message that isn't a "started" or
"finished" status update (English / French / Malagasy). The author gets a DM
explaining why (or a short auto-deleting channel message if their DMs are
off).

## 1. Create the bot on Discord

1. Go to https://discord.com/developers/applications → **New Application**, name it (e.g. "Telephone Tracker").
2. Left sidebar → **Bot** → **Add Bot**.
3. On the Bot page, turn on **MESSAGE CONTENT INTENT** under "Privileged Gateway Intents" (the bot needs this to read message text). Save changes.
4. Click **Reset Token** / **Copy** to get your bot token. Keep this secret — don't post it anywhere public or commit it to Git.

## 2. Invite it to your server

1. Left sidebar → **OAuth2 → URL Generator**.
2. Scopes: check `bot`.
3. Bot Permissions: check `View Channel`, `Send Messages`, `Manage Messages`.
4. Copy the generated URL, open it in your browser, pick your server, authorize.

## 3. Get your channel IDs

1. In Discord, go to User Settings → Advanced → turn on **Developer Mode**.
2. Right-click each "start/finish" tracker channel you want the bot to police → **Copy Channel ID**. You can watch as many channels as you like.
3. Optional: right-click a channel where you want the bot to post a log line every time it deletes a message (who, what they said, whether they got notified) → **Copy Channel ID**. This can be a separate mod-only channel. The bot needs **Send Messages** permission there too.

## 4. Install & configure

```bash
cd telephone-bot
pip install -r requirements.txt
```

Create a `.env` file in this folder (never commit it — it's already in `.gitignore`):

```bash
DISCORD_BOT_TOKEN="your-discord-token-here"
DISCORD_CHANNEL_IDS="123456789012345678,234567890123456789,345678901234567890"
DISCORD_LOG_CHANNEL_ID="456789012345678901"
ANTHROPIC_API_KEY="your-anthropic-key-here"
USE_CLASSIFIER="false"
```

`config.py` loads it automatically via `python-dotenv` — no manual `export`/`$env:` step needed. You can also set these as real environment variables instead if you prefer; `.env` just takes precedence-free defaults (a real env var already set will still win).

- `DISCORD_CHANNEL_IDS` is a **comma-separated list** — one or many channel IDs. You can also just edit `CHANNEL_IDS` directly in `config.py` instead of using the env var.
- `DISCORD_LOG_CHANNEL_ID` is optional — a single channel ID where the bot posts a line every time it deletes a message. Leave it unset to disable channel logging (the bot still logs to its console either way). You can also set `LOG_CHANNEL_ID` directly in `config.py`.
- `ANTHROPIC_API_KEY`: get one at https://console.anthropic.com/settings/keys (you'll need to add billing there — cost is tiny, a fraction of a cent per checked message since it uses a small/fast model). Only needed if `USE_CLASSIFIER` is true — see below.
- `USE_CLASSIFIER` defaults to `false` if unset. Set it to `true` to turn on the Claude classifier fallback (see below).

Alternatively, just paste any of these directly into `config.py`.

## 5. How matching works

0. **Forbidden words (always block):** if a message contains any word from
   `FORBIDDEN_KEYWORDS` in `config.py` (e.g. "tomorrow", "demain", "later",
   "plus tard") anywhere in it, it's blocked immediately — before the fast
   path, before the classifier, in every mode. This is what stops something
   like `"je commence demain"` from being let through just because it also
   contains "commence".

1. **Fast path (free, instant):** if a message exactly matches one of the
   words/phrases in `START_KEYWORDS` / `FINISH_KEYWORDS` in `config.py`
   (ignoring case, accents, emoji, and @mentions), it's allowed immediately
   — no API call. Good for the common case of someone just typing
   "started" or "vita".

2. **Claude classifier (fallback, when `USE_CLASSIFIER` is true — the
   default):** anything that doesn't exactly match falls through to a
   Claude API call (`classifier.py`) that reads the message and decides if
   it's genuinely a "starting/finishing **right now**" announcement — in
   any phrasing, in English, French, or Malagasy — versus something else.
   This is what lets `"Je vais commencer maintenant"` through while
   blocking `"Je vais commencer demain"`, even though both contain
   "commencer".

3. **Contains-keyword fallback (when `USE_CLASSIFIER` is false):** no
   Claude API calls are made at all. Instead, a message is allowed if it
   simply **contains** one of the `START_KEYWORDS` / `FINISH_KEYWORDS`
   words/phrases anywhere in it — no intent detection, so e.g. "starting
   tomorrow" would also be allowed since it contains "start". Use this
   mode if you don't want to set up an Anthropic API key at all, at the
   cost of that extra precision.

You can still edit `START_KEYWORDS` / `FINISH_KEYWORDS` in `config.py` to
add common exact phrases your group uses, to skip the API call for those.
I've included a few guessed Malagasy words (`manomboka` = start, `vita` =
done) — please double-check these with a native speaker.

If you ever want to tweak *how strict* the classifier is, edit the
`SYSTEM_PROMPT` in `classifier.py`.

## 6. Run it

```bash
python bot.py
```

Leave it running (e.g. on a small VPS, Raspberry Pi, or a free host like
Railway/Fly.io) so it stays online. If it goes offline, the channels just
won't be filtered until it's back.

## Notes

- The bot only touches the channels you configured — everywhere else is untouched.
- It needs the **Manage Messages** permission to delete messages; without it, it will log an error and leave messages alone.
- If a deleted message contained something you need to review (rare false positive), check the bot's console log — it logs the original text of everything it deletes.
- If `DISCORD_LOG_CHANNEL_ID` is set, every deletion also gets posted there: who posted it, what they said, and whether they got a DM or a channel fallback notice.
- If `USE_CLASSIFIER` is true and the Anthropic API key is missing or a classifier call fails for any reason, the bot fails **safe**: the message gets blocked rather than silently allowed through.
