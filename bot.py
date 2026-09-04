"""
Art Telephone tracker bot.

Watches the configured channels and only allows "started" / "finished"
status messages (English / French / Malagasy, configurable in config.py).
Anything else gets deleted, with a DM to the author explaining why (falls
back to a temporary channel message if their DMs are closed).
"""

import logging
import re
import unicodedata

import discord
from discord import app_commands

import config
from classifier import classify

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("telephone-bot")

# --- Build the normalized set of allowed messages -------------------------

_MENTION_RE = re.compile(r"<@!?\d+>|<@&\d+>|<#\d+>")
_CUSTOM_EMOJI_RE = re.compile(r"<a?:\w+:\d+>")
_UNICODE_EMOJI_RE = re.compile(
    "["
    "\U0001F300-\U0001FAFF"
    "\U00002600-\U000027BF"
    "\U0001F1E6-\U0001F1FF"
    "]+",
    flags=re.UNICODE,
)
_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)


def normalize(text: str) -> str:
    """Lowercase, strip accents/mentions/emojis/punctuation, collapse whitespace."""
    text = _MENTION_RE.sub("", text)
    text = _CUSTOM_EMOJI_RE.sub("", text)
    text = _UNICODE_EMOJI_RE.sub("", text)
    text = text.lower()
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    text = _PUNCT_RE.sub(" ", text)
    text = " ".join(text.split())
    return text


ALLOWED_START = {normalize(w) for w in config.START_KEYWORDS}
ALLOWED_FINISH = {normalize(w) for w in config.FINISH_KEYWORDS}
ALLOWED_ALL = ALLOWED_START | ALLOWED_FINISH
FORBIDDEN_ALL = {normalize(w) for w in config.FORBIDDEN_KEYWORDS}


async def is_allowed(content: str) -> bool:
    normalized = normalize(content)

    # Forbidden words always block, in every mode, before anything else —
    # e.g. "demain" (tomorrow) means this isn't a right-now announcement,
    # even if it also contains an otherwise-allowed keyword.
    if any(word in normalized for word in FORBIDDEN_ALL):
        return False

    # Fast path: exact match against the keyword lists, no API call needed.
    if normalized in ALLOWED_ALL:
        return True

    if not config.USE_CLASSIFIER:
        # No Claude calls in this mode: allow if a keyword appears anywhere
        # in the message (no intent detection, e.g. "later" phrasing isn't
        # distinguished from "now").
        return any(keyword in normalized for keyword in ALLOWED_ALL)

    # Fallback: ask Claude whether this is a genuine "starting/finishing
    # right now" announcement (handles phrasing/tense the fast path can't,
    # e.g. distinguishing "commence maintenant" from "commence demain").
    verdict = await classify(content)
    return verdict in ("START", "FINISH")


def is_admin(author: discord.abc.User) -> bool:
    """True if the message author has server Administrator permission —
    admins are exempt from moderation entirely."""
    return isinstance(author, discord.Member) and author.guild_permissions.administrator


# --- Bot --------------------------------------------------------------------

intents = discord.Intents.default()
intents.message_content = True  # Required to read message text
intents.guilds = True

client = discord.Client(intents=intents)
tree = app_commands.CommandTree(client)

log_channel: discord.abc.Messageable | None = None


@client.event
async def on_ready():
    global log_channel
    log.info("Logged in as %s (id=%s)", client.user, client.user.id)
    watched_channels = []
    for channel_id in config.CHANNEL_IDS:
        channel = client.get_channel(channel_id)
        if channel is None:
            log.warning(
                "Could not find channel with ID %s — check config.CHANNEL_IDS "
                "and that the bot has access to it.",
                channel_id,
            )
        else:
            log.info("Watching #%s in %s", channel.name, channel.guild.name)
            watched_channels.append(channel)

    if config.LOG_CHANNEL_ID:
        log_channel = client.get_channel(config.LOG_CHANNEL_ID)
        if log_channel is None:
            log.warning(
                "Could not find log channel with ID %s — check "
                "config.LOG_CHANNEL_ID and that the bot has access to it.",
                config.LOG_CHANNEL_ID,
            )
        else:
            log.info("Logging actions to #%s in %s", log_channel.name, log_channel.guild.name)

    guild_ids = {channel.guild.id for channel in watched_channels}
    if log_channel is not None:
        guild_ids.add(log_channel.guild.id)
    for guild_id in guild_ids:
        guild_obj = discord.Object(id=guild_id)
        tree.copy_global_to(guild=guild_obj)
        try:
            await tree.sync(guild=guild_obj)
        except discord.HTTPException:
            log.exception("Failed to sync the 'Check message' command to guild %s", guild_id)
    if guild_ids:
        log.info("Synced 'Check message' command to %d guild(s)", len(guild_ids))

    if config.CATCHUP_MESSAGE_LIMIT:
        for channel in watched_channels:
            await catch_up(channel)


async def catch_up(channel: discord.abc.Messageable) -> None:
    """Checks the last CATCHUP_MESSAGE_LIMIT messages in a channel for
    anything that should've been moderated while the bot was offline
    (missed reconnect gap, restart, etc.) and removes it."""
    log.info(
        "Catching up: checking last %d message(s) in #%s",
        config.CATCHUP_MESSAGE_LIMIT,
        channel.name,
    )
    async for message in channel.history(limit=config.CATCHUP_MESSAGE_LIMIT):
        if message.author.bot:
            continue
        if is_admin(message.author):
            continue
        if await is_allowed(message.content):
            continue
        await moderate_message(message, note="caught up after being offline")


async def send_log(text: str) -> None:
    if log_channel is None:
        return
    try:
        await log_channel.send(
            text, silent=True, allowed_mentions=discord.AllowedMentions.none()
        )
    except discord.Forbidden:
        log.error("Missing permission to send messages in the log channel.")


async def moderate_message(message: discord.Message, note: str = "") -> None:
    """Deletes a disallowed message and notifies its author, mirroring
    on_message's behavior. Shared by the startup/reconnect catch-up sweep
    and the "Check message" context menu command; `note` distinguishes
    which one in the logs."""
    author = message.author
    content_preview = message.content or "(empty / attachment / embed)"
    suffix = f" ({note})" if note else ""

    try:
        await message.delete()
    except discord.Forbidden:
        log.error(
            "Missing 'Manage Messages' permission in #%s — cannot delete messages.",
            message.channel.name,
        )
        return
    except discord.NotFound:
        pass  # already gone

    log.info("Deleted message from %s%s: %r", author, suffix, content_preview)

    dm_sent = False
    try:
        await author.send(config.DM_MESSAGE)
        dm_sent = True
    except discord.Forbidden:
        pass  # user has DMs closed

    fallback_sent = False
    if not dm_sent and config.CHANNEL_FALLBACK_REMINDER:
        try:
            await message.channel.send(
                f"{author.mention} this channel is only for start/finish "
                f"status updates — message removed.",
                delete_after=config.REMINDER_DELETE_AFTER,
            )
            fallback_sent = True
        except discord.Forbidden:
            log.error("Missing permission to send messages in the channel.")

    if dm_sent:
        notice = "DM sent"
    elif fallback_sent:
        notice = "channel fallback reminder sent (DMs closed)"
    else:
        notice = "no notification sent (DMs closed, fallback disabled or forbidden)"

    await send_log(
        f"🗑️ Deleted message from **{author}** in #{message.channel.name}{suffix}: "
        f"{content_preview!r} — {notice}"
    )


@tree.context_menu(name="Check message")
@app_commands.default_permissions(manage_messages=True)
async def check_message(interaction: discord.Interaction, message: discord.Message) -> None:
    """Right-click a message -> Apps -> Check message. Manually runs the
    same allow/delete decision on demand, for messages the automatic
    moderation didn't (or shouldn't have) touched."""
    await interaction.response.defer(ephemeral=True)

    if message.author.bot:
        await interaction.followup.send("That's a bot message — nothing to check.", ephemeral=True)
        return

    if is_admin(message.author):
        await interaction.followup.send(
            f"{message.author.mention} is an admin — always allowed, no action taken.",
            ephemeral=True,
        )
        return

    if await is_allowed(message.content):
        await interaction.followup.send("✅ Allowed — no action taken.", ephemeral=True)
        return

    await moderate_message(message, note=f"manual check by {interaction.user}")
    await interaction.followup.send(
        f"🗑️ Deleted and notified {message.author.mention}.", ephemeral=True
    )


@client.event
async def on_message(message: discord.Message):
    # Ignore other channels, DMs, bots (including itself)
    if message.author.bot:
        return
    if message.channel.id not in config.CHANNEL_IDS:
        return
    if is_admin(message.author):
        return

    if await is_allowed(message.content):
        return  # valid status update, leave it alone

    author = message.author
    content_preview = message.content or "(empty / attachment / embed)"

    try:
        await message.delete()
    except discord.Forbidden:
        log.error(
            "Missing 'Manage Messages' permission in #%s — cannot delete messages.",
            message.channel.name,
        )
        return
    except discord.NotFound:
        pass  # already gone

    log.info("Deleted message from %s: %r", author, content_preview)

    dm_sent = False
    try:
        await author.send(config.DM_MESSAGE)
        dm_sent = True
    except discord.Forbidden:
        pass  # user has DMs closed

    fallback_sent = False
    if not dm_sent and config.CHANNEL_FALLBACK_REMINDER:
        try:
            warning = await message.channel.send(
                f"{author.mention} this channel is only for start/finish "
                f"status updates — message removed.",
                delete_after=config.REMINDER_DELETE_AFTER,
            )
            fallback_sent = True
        except discord.Forbidden:
            log.error("Missing permission to send messages in the channel.")

    if dm_sent:
        notice = "DM sent"
    elif fallback_sent:
        notice = "channel fallback reminder sent (DMs closed)"
    else:
        notice = "no notification sent (DMs closed, fallback disabled or forbidden)"

    await send_log(
        f"🗑️ Deleted message from **{author}** in #{message.channel.name}: "
        f"{content_preview!r} — {notice}"
    )


if __name__ == "__main__":
    if not config.TOKEN:
        raise SystemExit(
            "No bot token found. Set the DISCORD_BOT_TOKEN environment "
            "variable or fill in config.py."
        )
    if not config.CHANNEL_IDS:
        raise SystemExit(
            "No channel IDs set. Set DISCORD_CHANNEL_IDS env var (comma-"
            "separated) or fill in config.py."
        )
    client.run(config.TOKEN)
