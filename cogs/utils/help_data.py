# cogs/utils/help_data.py
"""
Maps a cog's actual class name (e.g. "AntiNuke", "MusicCog") to display
metadata for the help panel: a friendly name, an emoji slug, a short
description, and search aliases a user might type.

This is the single source of truth for category display - the old help
command broke because it tried to guess a cog's class name from user input
via `.capitalize()`, which fails for anything but a single lowercase word
(e.g. "antinuke".capitalize() -> "Antinuke", but the real class is
"AntiNuke"). Here we match case-insensitively against the friendly name,
the real cog name, and any alias instead.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import List


@dataclass
class CategoryMeta:
    cog_name: str          # exact cog class name, e.g. "AntiNuke"
    display: str            # friendly name shown in the UI, e.g. "Anti-Nuke"
    emoji_slug: str          # key into emoji.json
    description: str
    aliases: List[str] = field(default_factory=list)


CATEGORIES: List[CategoryMeta] = [
    CategoryMeta("AntiNuke", "Anti-Nuke", "shield",
                 "Automated protection against server nukes and raids.",
                 ["antinuke", "anti-nuke", "security", "protection"]),
    CategoryMeta("Moderation", "Moderation", "hammer",
                 "Kick, ban, mute, warn, and other moderation tools.",
                 ["mod", "moderation"]),
    CategoryMeta("Role", "Roles", "tag",
                 "Create, assign, and manage server roles.",
                 ["roles", "role"]),
    CategoryMeta("TicketSystem", "Tickets", "ticket",
                 "Support ticket panels, transcripts, and controls.",
                 ["ticket", "tickets", "support"]),
    CategoryMeta("Giveaway", "Giveaways", "gift",
                 "Start, end, reroll, and manage giveaways.",
                 ["giveaway", "giveaways", "gwy"]),
    CategoryMeta("EmbedManager", "Embeds", "scroll",
                 "Build, send, and edit custom embeds.",
                 ["embed", "embeds"]),
    CategoryMeta("Greet", "Welcome", "wave",
                 "Greet new members when they join.",
                 ["welcome", "greet"]),
    CategoryMeta("Leveling", "Leveling", "trophy",
                 "XP, levels, leaderboard, work, and daily rewards.",
                 ["level", "levels", "xp", "rank"]),
    CategoryMeta("Wallet", "Wallet", "money",
                 "Litecoin wallet balance and address tools.",
                 ["wallet", "crypto", "ltc"]),
    CategoryMeta("Config", "Wallet Config", "gear",
                 "Configure wallet addresses, QR codes, and the shop.",
                 ["config", "settings"]),
    CategoryMeta("Games", "Games", "party",
                 "Blackjack, Wordle, Trivia, Connect 4, Battleship, and more.",
                 ["games", "game", "play"]),
    CategoryMeta("Engagement", "Community", "sparkle",
                 "Birthdays, marriage, achievements, and Never Have I Ever.",
                 ["engagement", "birthday", "marry", "community"]),
    CategoryMeta("Fun", "Fun", "sparkle",
                 "Memes, roasts, and other lighter commands.",
                 ["fun", "misc"]),
    CategoryMeta("Instagram", "Instagram", "camera",
                 "Look up Instagram profiles.",
                 ["instagram", "ig"]),
    CategoryMeta("MCStatus", "Minecraft", "ping",
                 "Check and track a Minecraft server's live status.",
                 ["minecraft", "mc"]),
    CategoryMeta("MusicCog", "Music", "music_note_beam",
                 "Play, queue, and control music in voice channels.",
                 ["music", "song", "voice"]),
    CategoryMeta("VCTTS", "Text-to-Speech", "speaker",
                 "Speak text-to-speech messages in a voice channel.",
                 ["tts", "voice", "vc"]),
    CategoryMeta("Utility", "Utility", "wrench",
                 "General-purpose utility and info commands.",
                 ["utility", "util", "info"]),
    CategoryMeta("dm", "DMs", "envelope",
                 "Owner-only DM tools.",
                 ["dm", "dms"]),
    CategoryMeta("ReactionRoles", "Reaction Roles", "tag",
                 "Self-assign roles by reacting to a message.",
                 ["reactionrole", "rr"]),
    CategoryMeta("ServerLogs", "Server Logs", "scroll",
                 "Audit trail for edits, deletes, joins, and more.",
                 ["logs", "log", "audit"]),
    CategoryMeta("AutoMod", "AutoMod", "shield",
                 "Chat filters: banned words, invites, spam.",
                 ["automod", "filter"]),
    CategoryMeta("Starboard", "Starboard", "star",
                 "Pin popular messages to a starboard channel.",
                 ["starboard", "star"]),
    CategoryMeta("Economy", "Economy", "coin",
                 "Coins, shop, gambling, and profile cards.",
                 ["economy", "coins", "shop", "profile"]),
    CategoryMeta("Reminders", "Reminders", "bell",
                 "Set a reminder and get DM'd when it's due.",
                 ["remind", "reminder"]),
    CategoryMeta("Polls", "Polls", "bar_chart",
                 "Button-voting polls with live results.",
                 ["poll", "vote"]),
    CategoryMeta("Suggestions", "Suggestions", "sparkle",
                 "Submit suggestions for staff to review.",
                 ["suggest", "suggestion"]),
    CategoryMeta("Tags", "Tags", "tag",
                 "Reusable staff-defined text snippets.",
                 ["tag", "tags", "snippet"]),
    CategoryMeta("Verification", "Verification", "shield_check",
                 "Click-to-verify gate for new members.",
                 ["verify", "verification"]),
    CategoryMeta("VoiceHubs", "Voice Hubs", "speaker",
                 "Join-to-create personal voice channels.",
                 ["voicehub", "vc"]),
    CategoryMeta("SocialFeeds", "Feeds", "megaphone",
                 "YouTube/Twitch notifications.",
                 ["feed", "youtube", "twitch"]),
    CategoryMeta("AIChat", "AI Chat", "robot",
                 "Ask the AI assistant a question.",
                 ["ai", "ask"]),
]

# quick lookup indexes, built once at import time
_BY_COG_NAME = {c.cog_name.lower(): c for c in CATEGORIES}
_BY_DISPLAY = {c.display.lower(): c for c in CATEGORIES}


def find_category(query: str) -> "CategoryMeta | None":
    """Case-insensitive lookup by cog class name, display name, or alias."""
    q = query.strip().lower()
    if not q:
        return None
    if q in _BY_COG_NAME:
        return _BY_COG_NAME[q]
    if q in _BY_DISPLAY:
        return _BY_DISPLAY[q]
    for cat in CATEGORIES:
        if q in (a.lower() for a in cat.aliases):
            return cat
    # loose partial match as a last resort (e.g. "tick" -> Tickets)
    for cat in CATEGORIES:
        if q in cat.display.lower() or q in cat.cog_name.lower():
            return cat
    return None


def meta_for_cog(cog_name: str) -> "CategoryMeta | None":
    return _BY_COG_NAME.get(cog_name.lower())
