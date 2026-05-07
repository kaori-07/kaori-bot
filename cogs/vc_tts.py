# cogs/vc_tts.py
"""
vc_tts cog - simple TTS utilities (with DM voice-note)

Commands:
- ,vn <voice?> <text>       -> generate an MP3 voice-note and send as attachment
- ,vc_say <voice?> <text>   -> join author's voice channel, speak text, then leave
- ,dm_vn <user> <voice?> <text> -> send a voice-note MP3 to the specified user via DM

Voice options (5):
- default   -> gTTS standard English (online) or pyttsx3 fallback
- uk        -> gTTS English UK accent (tld='co.uk') or pyttsx3 fallback
- au        -> gTTS English Australia (tld='com.au') or pyttsx3 fallback
- male      -> prefer pyttsx3 male voice (offline). Falls back to default.
- female    -> prefer pyttsx3 female voice (offline). Falls back to default.

Notes:
- Requires ffmpeg on PATH for best playback in voice channels.
- Optional: pip install gTTS and/or pyttsx3 to enable both backends.
- Limits text length to MAX_TTS_CHARS to avoid abuse.
"""

from __future__ import annotations

import asyncio
import os
import tempfile
import time
import typing
import re
from typing import Optional

import discord
from discord.ext import commands

# Optional backends
try:
    from gtts import gTTS  # online Google TTS
except Exception:
    gTTS = None

try:
    import pyttsx3  # offline TTS
except Exception:
    pyttsx3 = None

MAX_TTS_CHARS = 350
DEFAULT_LANG = "en"
CLEAN_FILENAME_LEN = 40

# mapping of logical voice keys to behavior
VOICE_KEYS = {
    "default": "default",
    "uk": "uk",
    "au": "au",
    "male": "male",
    "female": "female",
}


def _clean_filename(text: str) -> str:
    safe = "".join(c for c in text if c.isalnum() or c in (" ", "_", "-")).strip()
    if not safe:
        safe = "voice"
    return (safe[:CLEAN_FILENAME_LEN]).strip().replace(" ", "_")


async def _generate_tts_gtts_async(text: str, lang: str = DEFAULT_LANG, tld: Optional[str] = None) -> str:
    """Generate TTS using gTTS (blocking save; run in executor). Returns path."""
    if gTTS is None:
        raise RuntimeError("gTTS is not installed.")
    fd, tmp = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)

    def _save():
        if tld:
            t = gTTS(text=text, lang=lang, tld=tld)
        else:
            t = gTTS(text=text, lang=lang)
        t.save(tmp)
        return tmp

    loop = asyncio.get_event_loop()
    try:
        return await loop.run_in_executor(None, _save)
    except Exception:
        try:
            if os.path.exists(tmp):
                os.remove(tmp)
        except Exception:
            pass
        raise


def _generate_tts_pyttsx3_blocking(text: str, voice_preference: Optional[str] = None) -> str:
    """Generate TTS using pyttsx3 (blocking). Choose voice by preference 'male'/'female' if possible."""
    if pyttsx3 is None:
        raise RuntimeError("pyttsx3 not installed.")
    fd, tmp = tempfile.mkstemp(suffix=".mp3")
    os.close(fd)

    engine = pyttsx3.init()
    try:
        voices = engine.getProperty("voices") or []
        chosen = None
        if voice_preference in ("male", "female"):
            pref = voice_preference.lower()
            for v in voices:
                name = (getattr(v, "name", "") or "").lower()
                if pref in name:
                    chosen = v.id
                    break
            if chosen is None:
                if pref == "male" and len(voices) > 0:
                    chosen = voices[0].id
                elif pref == "female" and len(voices) > 1:
                    chosen = voices[-1].id
        if chosen:
            try:
                engine.setProperty("voice", chosen)
            except Exception:
                pass
        try:
            engine.setProperty("rate", 150)
        except Exception:
            pass
    except Exception:
        pass

    engine.save_to_file(text, tmp)
    engine.runAndWait()
    time.sleep(0.05)
    return tmp


class VCTTS(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot

    async def generate_tts_file(self, text: str, voice: str = "default") -> str:
        """
        Generate TTS and return filepath to mp3.
        voice: one of VOICE_KEYS: default, uk, au, male, female
        """
        voice = (voice or "default").lower()
        if voice not in VOICE_KEYS:
            voice = "default"

        # prefer gTTS for accents
        if voice in ("default", "uk", "au") and gTTS is not None:
            tld = None
            if voice == "uk":
                tld = "co.uk"
            elif voice == "au":
                tld = "com.au"
            try:
                return await _generate_tts_gtts_async(text, lang=DEFAULT_LANG, tld=tld)
            except Exception:
                if pyttsx3 is not None:
                    return await asyncio.get_event_loop().run_in_executor(None, lambda: _generate_tts_pyttsx3_blocking(text))
                raise

        if voice in ("male", "female") and pyttsx3 is not None:
            try:
                return await asyncio.get_event_loop().run_in_executor(None, lambda: _generate_tts_pyttsx3_blocking(text, voice))
            except Exception:
                if gTTS is not None:
                    return await _generate_tts_gtts_async(text, lang=DEFAULT_LANG)
                raise

        if gTTS is not None:
            return await _generate_tts_gtts_async(text, lang=DEFAULT_LANG)
        if pyttsx3 is not None:
            return await asyncio.get_event_loop().run_in_executor(None, lambda: _generate_tts_pyttsx3_blocking(text))
        raise RuntimeError("No TTS backend available. Install gTTS (online) or pyttsx3 (offline).")

    def _parse_voice_and_text(self, arg_string: str) -> typing.Tuple[str, str]:
        """
        Parse optional voice key at start of arg string.
        Examples:
          "uk hello there" -> voice='uk', text='hello there'
          "hello there" -> voice='default', text='hello there'
          "male:hello" or "male|hello" -> supported too
        """
        if not arg_string:
            return "default", ""
        parts = arg_string.strip().split(None, 1)
        if not parts:
            return "default", ""
        # voice:text or voice|text style
        if ":" in arg_string or "|" in arg_string:
            sep = ":" if ":" in arg_string else "|"
            left, right = arg_string.split(sep, 1)
            left = left.strip().lower()
            if left in VOICE_KEYS:
                return left, right.strip()
        first = parts[0].strip()
        if first.lower() in VOICE_KEYS:
            if len(parts) == 1:
                return first.lower(), ""
            return first.lower(), parts[1].strip()
        return "default", arg_string.strip()

    @commands.command(name="vn")
    async def vn(self, ctx: commands.Context, *, args: str):
        """
        Generate voice note mp3 and send it.
        Usage:
          ,vn Hello world
          ,vn uk Hello (use UK accent)
          ,vn male Hello (use male voice if available)
          ,vn uk:Hello (also supported)
        """
        if not args or not args.strip():
            return await ctx.send("<a:Cross_:1489174755537064046> Please provide text to convert to a voice note. Usage: `,vn <voice?> <text>`")

        voice_key, text = self._parse_voice_and_text(args)
        if not text:
            return await ctx.send("<a:Cross_:1489174755537064046> No text provided after voice selection. Usage: `,vn <voice?> <text>`")

        if len(text) > MAX_TTS_CHARS:
            return await ctx.send(f"<a:Cross_:1489174755537064046> Text too long. Limit: {MAX_TTS_CHARS} characters.")

        status = await ctx.send("🔊 Generating voice note...")

        try:
            mp3_path = await self.generate_tts_file(text, voice=voice_key)
        except Exception as e:
            await status.edit(content=f"<a:Cross_:1489174755537064046> TTS generation failed: {e}")
            return

        try:
            filename = f"{_clean_filename(text)[:24]}_{voice_key}.mp3"
            await ctx.send(file=discord.File(mp3_path, filename=filename))
            await status.delete()
        except Exception as e:
            await status.edit(content=f"<a:Cross_:1489174755537064046> Failed to send file: {e}")
        finally:
            try:
                if os.path.exists(mp3_path):
                    os.remove(mp3_path)
            except Exception:
                pass

    @commands.command(name="vc_say")
    async def vc_say(self, ctx: commands.Context, *, args: str):
        """
        Join the user's voice channel and speak text, then leave.
        Usage:
          ,vc_say Hello everyone
          ,vc_say female Hello
        """
        if not args or not args.strip():
            return await ctx.send("<a:Cross_:1489174755537064046> Please provide text to speak. Usage: `,vc_say <voice?> <text>`")

        voice_key, text = self._parse_voice_and_text(args)
        if not text:
            return await ctx.send("<a:Cross_:1489174755537064046> No text provided after voice selection. Usage: `,vc_say <voice?> <text>`")

        if len(text) > MAX_TTS_CHARS:
            return await ctx.send(f"<a:Cross_:1489174755537064046> Text too long. Limit: {MAX_TTS_CHARS} characters.")

        author = ctx.author
        if not getattr(author, "voice", None) or not author.voice.channel:
            return await ctx.send("<a:Cross_:1489174755537064046> You must be connected to a voice channel for me to speak there.")

        channel = author.voice.channel
        status = await ctx.send(f"🔊 Joining `{channel.name}` and speaking...")

        try:
            mp3_path = await self.generate_tts_file(text, voice=voice_key)
        except Exception as e:
            await status.edit(content=f"<a:Cross_:1489174755537064046> TTS generation failed: {e}")
            return

        vc: Optional[discord.VoiceClient] = discord.utils.get(self.bot.voice_clients, guild=ctx.guild)
        try:
            if vc and vc.is_connected():
                try:
                    await vc.move_to(channel)
                except Exception:
                    pass
            else:
                vc = await channel.connect(timeout=10.0, reconnect=True)
        except Exception as e:
            await status.edit(content=f"<a:Cross_:1489174755537064046> Could not connect to voice channel: {e}")
            try:
                if os.path.exists(mp3_path):
                    os.remove(mp3_path)
            except Exception:
                pass
            return

        try:
            if not os.path.exists(mp3_path):
                raise RuntimeError("TTS file missing after generation.")
            source = discord.FFmpegPCMAudio(mp3_path)
            player = discord.PCMVolumeTransformer(source, volume=1.0)
            vc.play(player)
            timeout = 60
            waited = 0
            while vc.is_playing() or vc.is_paused():
                await asyncio.sleep(0.5)
                waited += 0.5
                if waited >= timeout:
                    break
            await status.edit(content="<a:tick:1489157731393994854> Finished speaking.")
        except Exception as e:
            await status.edit(content=f"<a:Cross_:1489174755537064046> Playback error: {e}")
        finally:
            try:
                if os.path.exists(mp3_path):
                    os.remove(mp3_path)
            except Exception:
                pass
            try:
                await asyncio.sleep(0.5)
                if vc and vc.is_connected():
                    await vc.disconnect()
            except Exception:
                pass

    @commands.command(name="dm_vn")
    async def dm_vn(self, ctx: commands.Context, user: typing.Union[discord.User, discord.Member], *, args: str):
        """
        Generate a voice-note mp3 and DM it to the specified user.
        Usage:
          ,dm_vn @user Hello
          ,dm_vn 123456789012345678 uk Hello
          ,dm_vn username#1234 female:Hello
        Notes:
          - The 'user' parameter accepts mention, id, or username lookup via Discord converter.
          - The text may optionally start with voice key (see ,vn).
        """
        if not user:
            return await ctx.send("<a:Cross_:1489174755537064046> Please specify a user to DM the voice note to.")

        if not args or not args.strip():
            return await ctx.send("<a:Cross_:1489174755537064046> Please provide text to convert to a voice note. Usage: `,dm_vn <user> <voice?> <text>`")

        voice_key, text = self._parse_voice_and_text(args)
        if not text:
            return await ctx.send("<a:Cross_:1489174755537064046> No text provided after voice selection. Usage: `,dm_vn <user> <voice?> <text>`")

        if len(text) > MAX_TTS_CHARS:
            return await ctx.send(f"<a:Cross_:1489174755537064046> Text too long. Limit: {MAX_TTS_CHARS} characters.")

        status = await ctx.send(f"🔊 Generating voice note to DM {user}...")

        try:
            mp3_path = await self.generate_tts_file(text, voice=voice_key)
        except Exception as e:
            await status.edit(content=f"<a:Cross_:1489174755537064046> TTS generation failed: {e}")
            return

        try:
            filename = f"{_clean_filename(text)[:24]}_{voice_key}.mp3"
            try:
                await user.send(file=discord.File(mp3_path, filename=filename))
                await status.edit(content=f"<a:tick:1489157731393994854> Sent voice note to {user}.")
            except discord.Forbidden:
                await status.edit(content=f"<a:Cross_:1489174755537064046> Could not DM {user}. They may have DMs disabled or blocked the bot.")
            except Exception as e:
                await status.edit(content=f"<a:Cross_:1489174755537064046> Failed to send DM: {e}")
        finally:
            try:
                if os.path.exists(mp3_path):
                    os.remove(mp3_path)
            except Exception:
                pass

async def setup(bot: commands.Bot):
    await bot.add_cog(VCTTS(bot))
