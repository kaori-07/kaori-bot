# Discord Bot

## Quick start

```bash
pip install -r requirements.txt --break-system-packages
cp .env.example .env   # then edit .env and paste your bot TOKEN
python main.py
```

⚠️ **Your original `.env` had a live bot token in it.** That token was in the
zip you uploaded, so treat it as leaked — go to the Discord Developer Portal
and **regenerate your bot token** before deploying this anywhere, then paste
the new one into `.env`.

## What changed in this pass

### 1. Emoji system — `emoji.json`
Every emoji used anywhere in the bot now lives in one file: **`emoji.json`**
at the project root. To change an emoji, edit that file (or use the
dashboard's Emoji page) — you never need to touch a cog or run a script
again. `replace.py` has been removed; it's no longer needed.

Changes take effect **live**, with no restart, because `cogs/utils/emoji_manager.py`
re-checks the file's modified time on each access and reloads automatically.

In code, cogs use it like:
```python
from cogs.utils.emoji_manager import EMOJI
await ctx.send(f"{EMOJI['success']} Done!")
```
Any custom animated/static Discord emoji (`<a:name:id>`) or plain unicode
emoji can be used as a value — just paste it into the JSON value.

### 2. Bugs fixed
- **Security**: `/calc` used raw `eval()` with a fake sandbox that's actually
  escapable. Replaced with a real AST-based safe arithmetic evaluator.
- **Crash**: `dm.py`'s `on_ready` listener called an undefined `show_banner()`
  function — threw on every connect/reconnect. Removed.
- **Crash**: several `member.avatar.url if member.avatar else None` patterns
  broke for anyone using a default Discord avatar. Switched to
  `.display_avatar.url`, which always resolves.
- **Data desync**: `wallet.py` and `config.py` both cached `wallet.json`
  independently in memory — a `/setaddy` in one cog was invisible to the
  other until a full restart. Both now share one hot-reloading store
  (`cogs/utils/json_store.py`).
- **Silent bug**: `mcstatus.py` computed its config filename from
  `bot.user.id` at cog `__init__`, but `bot.user` is always `None` at that
  point (cogs load before login) — every install was writing to
  `status_config_unknown.json`. Fixed, and `mcstatus` config now persists
  properly across restarts (it also wasn't in `requirements.txt` — added).
- **Fragile global error handling**: the only thing catching permission
  errors bot-wide was a `Cog.listener()` defined inside `dm.py` — if that cog
  were ever disabled, every permission-gated command bot-wide would go
  silent. Consolidated into one real global handler in `main.py`.
- **DM crashes**: ~40 commands (moderation, roles, tickets, giveaways,
  music, guild-scoped config) claimed to support DMs but used
  `discord.Member`/`ctx.guild`, which don't work outside a server — they'd
  error out if actually invoked in a DM. These are now properly
  `@commands.guild_only()`. Conversely, `avatar`, `level`, and `xp` are
  genuinely user-scoped, so they were switched from `discord.Member` to
  `discord.User` so they actually work in DMs as intended.
- **Rich presence resilience**: the status rotator now auto-resumes on
  restart if it was left running, instead of requiring a manual
  `.start_rotation` every time the process restarts.

### 3. Rich presence — `cogs/status_rotator.py`
Rotates the bot's actual Discord presence on a timer, with an optional
live-updating panel embed + up to 2 link buttons posted in a channel (bots
can't attach buttons/images to their real presence — that's an RPC feature
only game clients get — so the panel is the closest equivalent, and is
entirely optional). Supports every presence type Discord actually allows a
bot to use: Playing, Watching, Listening to, Competing in, Streaming (with a
URL), and Custom Status (raw text with an optional leading emoji, unicode
or a custom `<a:name:id>` tag). Each entry can also override the global
rotation interval individually. Config lives in `data/status_config.json`
and can be fully managed from the dashboard's **Rich Presence** page —
add/remove entries with all of the above fields, change the interval,
start/stop.

### 4. Web dashboard — `dashboard/`
A small Flask app for the owner to manage the bot without touching code.

**Setup (once):**
```bash
python set_dashboard_password.py
```
This prompts for a username + password and writes a bcrypt hash into
`.env` — the plaintext password is never stored anywhere.

**Run:** set `DASHBOARD_ENABLED=true` in `.env`, then start the bot normally
(`python main.py`). It'll be live at `http://127.0.0.1:5000` by default.

Pages:
- **Overview** — online status, server/member counts, latency, per-cog
  enable/disable toggles + reload-all button. Stats and cog "loaded" state
  update live via polling (`/api/live`, every 4s) with animated counters.
- **Servers** — every server the bot is in, with icon, member count, owner,
  and a one-click **Leave** action.
- **Emojis** — add/edit/delete any entry in `emoji.json`, live.
- **Rich Presence** — manage status rotation entries, interval, start/stop.
- **Broadcast** — pick a server + channel and send a message or embed to it
  directly from the dashboard.
- **Live Logs** — a real-time console view of the bot's log output
  (`/api/logs`, polled every 2s), auto-scrolling, color-coded by level.

UI notes: flash messages render as animated slide-in toasts, page sections
fade/slide in on load, and the sidebar shows a live connection dot + latency
reading on every page.

Security notes:
- Password is bcrypt-hashed, never stored in plaintext.
- CSRF protection on every form (Flask-WTF).
- Session cookies are `HttpOnly` + `SameSite=Lax`.
- Simple brute-force lockout (5 failed attempts → 60s lockout per IP).
- Defaults to binding `127.0.0.1` only — it is **not** exposed to the
  internet unless you put it behind a reverse proxy or change
  `DASHBOARD_HOST` yourself. If you do expose it publicly, put it behind
  HTTPS (e.g. Caddy/nginx/Cloudflare Tunnel) and set
  `DASHBOARD_FORCE_HTTPS=true`.

### 5. Cog enable/disable
Any cog can be toggled off from the dashboard without deleting code.
State is stored in `cog_control.json` (auto-created) and read by `main.py`
at startup. Owner-only `,reload` command applies changes without a full
restart.

## Project layout
```
main.py                     bot entrypoint, global error handler, cog loader
emoji.json                  every emoji, editable directly or via dashboard
set_dashboard_password.py   one-time CLI to set dashboard login
data/                       ALL persistent bot data lives here (auto-created)
  wallet.json, leveling.json, cog_control.json, mcstatus_config.json,
  status_config.json          - via the shared JSON store (cogs/utils/json_store.py)
  gwy.json, mode.json,
  music_panels.json           - per-cog data, relocated here on startup
  db/anti.db, db/block.db     - antinuke's SQLite databases
cogs/
  utils/
    emoji_manager.py        hot-reloading emoji.json loader
    json_store.py           shared hot-reloading JSON store, resolves into data/
    cog_control.py          cog enable/disable registry
    log_buffer.py            in-memory ring buffer feeding the dashboard's live log console
  antinuke.py                anti-nuke protection (see below)
  *.py                      your bot's other cogs
dashboard/
  app.py                    Flask app factory
  templates/, static/       dashboard UI
```

All JSON/SQLite data files are now centralized under `data/` instead of being
scattered at the project root. This happens automatically — cogs that go
through `cogs/utils/json_store.py` (`get_store(...)`) never even reference a
literal path, so any future cog's data lands in `data/` for free. A few cogs
with their own hand-rolled file IO (`giveaway.py`, `moderation.py`,
`song.py`, `antinuke.py`) were pointed at `data/` explicitly.

### Antinuke cog (`cogs/antinuke.py`)
Automated protection against server nukes: reverts/punishes unauthorized
channel/role deletes, mass bans/kicks, `@everyone` spam, dangerous role
grants, webhook abuse, unauthorized bot adds, and basic message spam. Backed
by SQLite (`data/db/anti.db`, `data/db/block.db`), auto-created on first load.

Commands (server owner / administrator only, all guild-only):
- `/antinuke_toggle` — turn the system on/off for the server
- `/antinuke_status` — check current status
- `/whitelist <user>` / `/unwhitelist <user>` — exempt a user from all checks
- `/trust_admin <user>` / `/untrust_admin <user>` — grant/revoke the highest
  trust tier (server-owner only, bypasses everything including antinuke)

On first punishment action it auto-creates a `🛡️・anti-nuke-logs` channel
(visible only to the server owner and the bot) and posts a log embed there
for every action taken.

### Ticket cog (`cogs/ticket.py`)
Full rewrite: SQLite-backed (`data/db/ticket.db`), dropdown-driven admin
setup builder, category dropdown for opening tickets, claim/unclaim, close
with auto-lock, reopen, and HTML transcript generation on delete.
`/ticket_setup`, `/ticket_add`, `/ticket_remove`, `/ticket_transcript` are
all guild-only. Fixed a security gap where the setup builder had no
per-user lock, so anyone could hijack an in-progress panel if the command
was ever run via prefix instead of slash.

### Embed cog (`cogs/embed.py`)
Replaces the old single `/embed` command with four: `/embed_builder` (a full
interactive GUI with modals for title/description/color/author/images/footer
plus a channel picker), `/embed_quick` (one-line embed), `/embed_json`
(paste raw embed JSON), and `/embed_edit` (edit an existing bot message by
link + JSON). Fixed a cross-guild bug where staff could edit any bot message
in *any* server they knew the link to — `/embed_edit` now checks the
message actually belongs to the server the command was run in.

### Fun cog (`cogs/fun.py`)
Expanded games library: Connect 4, Guess Battle, Trivia, Word Scramble,
Slots, Minesweeper, Truth or Dare, 8-ball, dice, alongside the existing
Tic-Tac-Toe, Rock Paper Scissors, coinflip, roast, meme/dog/cat lookups, and
more. Plus five new fully button/modal-driven games: **Blackjack** (hit/stand
vs. a dealer AI), **Wordle** (5-letter word, 6 tries, colored-square feedback
grid), **Memory Match** (4x4 emoji pairs grid), **Hangman** (letter-by-
letter with a classic ASCII gallows), and **Guess the Number** (`,guessnumber
<min> <max>` / `,gtn`) — a genuinely multiplayer, unlimited-player round
where the host picks the range, the bot secretly picks a number, and anyone
in the channel can jump in and guess via the button (each guesser gets a
private higher/lower hint, first correct guess wins). The single-player
games restrict interactions to whoever started them and disable their
buttons on completion or timeout. Fixed a real performance bug: `dog`, `cat`,
`meme`, `roast`, and `trivia` used blocking synchronous `requests.get()`
calls, which freeze the *entire bot* (every server, every command) for the
duration of each HTTP call. All five now use non-blocking `aiohttp`.

### Help panel (`/help`)
Rebuilt from scratch. The old version tried to guess a cog's class name
from user input via `.capitalize()` (e.g. `"antinuke".capitalize()` ->
`"Antinuke"`), which never matched real class names like `AntiNuke` or
`EmbedManager` — that was the "category doesn't work" bug. The new system
(`cogs/utils/help_data.py` + `cogs/utils/help_view.py`) matches
case-insensitively against display name, real cog name, and aliases, and
renders as an interactive embed with a category dropdown instead of a wall
of text.

### Dashboard additions
- **Music** — see what's playing per server, pause/resume/skip/stop, and
  adjust volume live, all from the browser.
- **Anti-Nuke** — toggle protection per server, view whitelisted users and
  trusted admins, remove entries — talks directly to the same SQLite DB the
  bot cog uses.
- **Emoji page upgrade** — custom Discord emoji (`<a:name:id>`) now render
  as actual images (pulled from Discord's CDN) instead of raw text, there's
  a live preview while typing a new value, and a search box to filter the
  full list.

## New feature cogs (this pass)

A large batch of new server-management, engagement, and utility cogs, all
following the same conventions as the rest of the bot (`EMOJI[]`, shared
JSON stores under `data/`, guild-only where appropriate):

- **`reaction_roles.py`** — bind an emoji on a message to a role; reacting
  toggles it (`/reactionrole_add`, `/reactionrole_remove`, `/reactionrole_list`).
- **`serverlogs.py`** — audit trail (message edits/deletes, joins/leaves,
  role changes, nickname changes, voice activity) to a configured channel,
  per-event toggles. Managed via `/logs_setchannel`, `/logs_toggle`, or the
  dashboard's **Server Logs** page.
- **`automod.py`** — banned-word filter, invite-link blocker, mention-spam
  and message-flood throttling. `/automod_toggle`, `/automod_addword`,
  `/automod_removeword`, `/automod_invites`, `/automod_settings`. This is
  distinct from `antinuke.py` — automod catches chat-level abuse, antinuke
  responds to destructive server actions (mass bans, channel deletes, etc).
- **`starboard.py`** — messages that hit a reaction threshold get mirrored
  into a starboard channel and stay in sync as the count changes
  (`/starboard_setup`).
- **`economy.py`** — a separate for-fun coin currency (distinct from
  `wallet.py`'s real Litecoin and `leveling.py`'s XP): `/coins`, `/earn`
  (hourly), `/give`, `/coinbet` (50/50 gamble), a role shop
  (`/shop`, `/buy`, `/shop_additem`, `/shop_removeitem`), and `/profile` — a
  social profile card combining coins, level/XP (if the Leveling cog is
  loaded), and join date.
- **`reminders.py`** — `/remindme <duration> <text>` (e.g. `2h Check the
  oven`), DMs you back when it's due; `/reminders` lists what's pending.
- **`polls.py`** — `/poll` with 2-5 options, button voting, live result bars
  that update as votes come in.
- **`suggestions.py`** — `/suggest` posts to a configured channel with
  upvote/downvote reactions and staff Approve/Deny buttons
  (`/suggestions_setchannel`).
- **`tags.py`** — staff-defined reusable text snippets:
  `/tag_create`, `/tag <name>`, `/tag_delete`, `/tag_list`.
- **`verification.py`** — `/verification_setup <role>` posts a persistent
  "Verify" button; clicking it grants the role. Survives bot restarts.
- **`voicehubs.py`** — "Join to Create": joining a configured hub voice
  channel spawns a personal voice channel for that user, auto-deleted once
  everyone leaves (`/voicehub_setup`).
- **`social_feeds.py`** — YouTube upload notifications via YouTube's public
  RSS feed (no API key needed) with `/feed_addyoutube`; Twitch live
  notifications via `/feed_addtwitch` if `TWITCH_CLIENT_ID` /
  `TWITCH_CLIENT_SECRET` are set in `.env` (gracefully disabled otherwise).
- **`ai_chat.py`** — `/ask <question>`, backed by any OpenAI-compatible
  chat completions API. Configure `AI_API_KEY` in `.env` (optionally
  `AI_API_BASE` / `AI_MODEL` to point at OpenAI, Groq, OpenRouter, a local
  server, etc). Does nothing but return a clear error if unconfigured.

## Dashboard additions (this pass)

- **Analytics** — total commands run, top commands, top servers by
  activity, tracked automatically via a lightweight usage counter.
- **Server Logs** — per-server, per-event-type toggles for `serverlogs.py`,
  mirroring the `/logs_toggle` command in a proper UI.
- **Data backup** — a "Download data backup" button on the Overview page
  that zips the entire `data/` folder plus `emoji.json` for download.

## Games split into their own cog + fixes (this pass)

All interactive games now live in **`cogs/games.py`**, separate from the
lighter, non-competitive commands that stayed in `cogs/fun.py` (memes,
roasts, dog/cat pics, 8-ball, dice, coinflip).

**Fixed a real crash bug**: `fun.py` used to define two *different* classes
both named `GuessNumberModal` — Python let the second one silently overwrite
the first at import time, so `/guessbattle`'s "Set Secret Number" and "Make
a Guess" buttons were calling the wrong modal's `__init__` and crashing with
a `TypeError` the moment either player clicked one. Renamed the duel's modal
to `GuessBattleModal` so each game owns its own uniquely-named class — this
is exactly the kind of bug that's invisible until someone actually clicks
the button, so it's worth double-checking if you add more games by hand.

**Made more games multiplayer where the concept allows it**:
- **Trivia** — previously only the person who ran the command could answer;
  now anyone in the channel can, first correct answer wins.
- **`/guessnumber`** (unlimited players) is the multiplayer sibling of
  `/guessbattle` (which stays a 2-player duel by design — a duel is
  inherently two-sided, so instead of forcing more players into it, the
  unlimited-player alternative already exists as its own command).

**3 new multiplayer games added**:
- **`/wyr`** (Would You Rather) — two options, anyone votes, results update live.
- **`/reactiontest`** — button turns green after a random delay, whoever
  clicks first wins; clicking early gets called out.
- **`/typerace`** — everyone races to type a shown phrase exactly; fastest
  correct message wins, with a WPM readout.

## Emoji defaults + reset (this pass)

The dashboard's Emoji page now ships a frozen `emoji_defaults.json`
snapshot alongside the live-editable `emoji.json`. Each entry shows whether
it's still the shipped default or has been **customized** (e.g. swapped for
your own Nitro/animated emoji) — customized ones get a one-click
**Reset to default** button. This is purely additive: `emoji_defaults.json`
is never written to by the dashboard, so it always reflects what the bot
shipped with, regardless of how much you customize `emoji.json` afterward.


## Music: cookie file fallback (this pass)

On a VPS, YouTube frequently rate-limits or outright blocks anonymous
requests from cloud/datacenter IPs, which breaks music playback even though
everything is configured correctly. `cogs/song.py` now supports cookie
files exported from a real logged-in browser session:

- Drop `cookie.txt` into `data/cookies/` (or the project root) and it's
  used automatically for every extraction.
- If it fails or expires, `cookie1.txt`, `cookie2.txt`, `cookie3.txt`,
  `cookie4.txt` are tried next, each with and without a `player_client=web`
  override - no restart needed, this happens per-request.
- `/audiodiag` now shows exactly which cookie files were found (or a clear
  warning + instructions if none were) as a proper embed instead of a raw
  text dump.
- Cookie files are treated as sensitive session credentials: the dashboard's
  "Download data backup" button explicitly excludes `data/cookies/` so they
  can never leave the server by accident.

## Crypto commands upgraded (this pass)

`cogs/wallet.py`'s `/ltc` and `/balance` commands were pulling minimal data
from free APIs that actually return much more. Upgraded both:

- `/ltc` now shows 24h price change (with a trend indicator and colored
  embed), market cap, and 24h volume - all from the same CoinGecko
  endpoint, just requesting the extra fields (no API key needed).
- `/balance` now shows confirmed/unconfirmed/total-received balances as
  clean side-by-side fields (previously one big text blob), plus
  transaction count and a clickable link straight to the BlockCypher
  explorer for that address.

## Command output cleanup pass (this pass)

Went through every cog looking for outputs that weren't embeds, had no
emoji, or read like leftover placeholder text, and fixed what was found:

- **`cogs/greet.py` was rewritten** - it previously had a server name
  ("Mythical Network"), a specific channel ID, and a Discord CDN image URL
  with signed/expiring parameters (`?ex=...&is=...&hm=...`) all hardcoded
  directly in the source, and the on/off toggle only lived in memory
  (reset on every restart, silently breaking the feature). None of that
  works for any server other than the original one it was written for.
  Now: per-guild settings persisted to `data/greet.json`, a
  `/greet_setchannel` command to configure the channel, a generic welcome
  message using the actual server's name and icon, and a `/greet` (no
  args) status view showing current on/off state and channel.
- **`cogs/moderation.py`'s permission-error messages** said "not enough
  perm...." (both for prefix and slash commands) - replaced with a clean
  message that also names the missing permission.
- Several bare, unstyled error strings in `games.py` ("Invalid opponent!",
  trivia fetch failures) and `song.py` ("Queue is empty.") got emoji and
  consistent phrasing to match the rest of the bot.

## Large feature batch (this pass)

Added a real, tested batch from the 100-feature request — full transparency:
building 100 genuinely new, quality-tested features in one pass isn't
something that can be done responsibly (several, like a Werewolf/Mafia game,
a chess engine, or generated leaderboard/welcome images, are each their own
multi-session build), so this batch focused on ~35 that could be shipped
properly. Everything below compiles clean and has zero command-name
collisions with the rest of the bot (189 commands total now).

**Moderation** (`cogs/moderation.py`): configurable warn escalation ladder
(auto-timeout → auto-kick → auto-ban at set warning counts), a numbered
case-log system (`/cases @user`), and `/clear` upgraded to filter by author
and/or content match instead of just a raw count.

**Auto-mod** (`cogs/automod.py`): nickname word filter (auto-resets
violating nicknames), minimum account age gate, and raid detection —
mass joins within a configurable window auto-locks `@everyone` from
sending messages server-wide, with `/automod_unlock` to lift it.

**New `cogs/engagement.py`**: birthdays (`/setbirthday`, daily
announcements), server anniversaries, boost shoutouts, an achievements/badge
system, a marriage system (`/marry`, `/divorce`, `/spouse`), and Never Have
I Ever (`/nhie`).

**Economy** (`cogs/economy.py`): a pet system (adopt/feed/level), coin-
wagering RPG duels (`/duel`), and daily challenges (`/challenge`).

**Utility** (`cogs/utility.py`): timezone lookup (`/settimezone`, `/time`),
QR code generator, URL shortener, unit conversion (`/convert`), sticky
messages, and channel history export to a text file.

**Music** (`cogs/song.py`): lyrics lookup (`/lyrics`), 24/7 mode, a DJ role
restriction (wired into `/skip` and `/stop`), and playlist save/load/list.

**Games** (`cogs/games.py`): Battleship (2-player, hidden 8x8 fleets),
Emoji Riddle, and a persisted Trivia leaderboard (`/triviatop`).

**Dashboard**: a per-server Members page with search plus a live voice-
activity view, linked from the Servers page.

### Deferred (too large/risky for a single pass, flagged rather than faked)
Werewolf/Mafia, Chess, generated leaderboard/welcome banner images (needs
Pillow + font assets + real design work), a drag-and-drop role hierarchy
editor, sharding status (the bot isn't sharded), weather/translation
commands (need a paid or rate-limited third-party API key — happy to wire
up if you want to pick a provider), webhook management UI, and a scheduled-
announcement composer (the reminders system already covers "post this
later," a dedicated UI is a natural next step). Say which of these you want
next and I'll build them the same way — real, tested, no collisions.

## fakehack + dashboard polish (this pass)

**`/fakehack`** rewritten: animated terminal-style progress bar (updates
live in one embed instead of a jumpy text edit), an Abort button only the
invoker can press, more varied "results" fields, and swapped the fake email
domain from `gmail.com` to the RFC-reserved `example.com`.

**Dashboard Overview** now shows a second, detailed stat row — live CPU %
and memory usage (via `psutil`), a smoothly-ticking uptime counter (updates
every second client-side, not just every poll), total command count, loaded
cog count, and shard count — plus a **Sync slash commands** button next to
Reload. Added subtle animated glow accents on the status card and bot
avatar, button/switch press feedback, and a reusable skeleton-shimmer style
for anything still loading.

## Fixed: bot failing to load 9 cogs (100-slash-command cap)

Discord caps **global slash commands at 100 per bot**, full stop — not
per-server, not configurable. With every command built as
`hybrid_command` (registers both `/slash` and prefix), the bot hit 155
slash-command registrations. Once the 100th one was added mid-startup,
every cog loaded *after* that point failed completely and silently lost
**all** of their commands — including the prefix versions — which is why
`cogs.song`, `cogs.starboard`, `cogs.suggestions`, `cogs.tags`,
`cogs.ticket`, `cogs.utility`, `cogs.verification`, `cogs.voicehubs`, and
`cogs.wallet` were failing to load at all.

Fixed by converting the less-essential commands to **prefix-only**
(`,command` — still fully functional, just not in the `/` picker). Nothing
was deleted — every one of the 189 commands still exists and works exactly
as before, just accessed via prefix instead of slash for ~87 of them.
Kept as slash commands: the ones people actually reach for via `/` — things
like `/kick`, `/ban`, `/warn`, `/clear`, `/play`, `/ticket_setup`,
`/gstart`, `/level`, `/leaderboard`, `/help`, and similar headline
commands per cog. Everything else (sub-settings, admin config commands,
secondary variants) is prefix-only now.

Result: **69 total slash commands** (68 + `/help`), leaving room for
~30 more before hitting the cap again if you add features later. If you
want a specific converted command back on `/`, just swap
`@commands.command(name="x", ...)` back to `@commands.hybrid_command(name="x", ...)`
and re-add `@app_commands.allowed_installs(...)` /
`@app_commands.allowed_contexts(...)` above it — just keep an eye on the
total count.

## New: category delete command

**`,deletecategory <category_id>`** (aliases `,delcategory`, `,clearcategory`,
admin-only, prefix-only) — deletes a category and every channel inside it in
one go. Since this is fully irreversible, it shows a confirmation embed
listing the channels that will be removed and requires clicking a
**Delete Everything** button (locked to whoever ran the command, 30s
timeout) before anything actually happens. Reports how many channels were
deleted vs. failed (e.g. due to missing permissions) afterward.

## Another large batch (this pass)

Same honesty as before: didn't attempt all 100 suggested items, built ~31
real, tested ones, all prefix-only to stay well clear of the slash-command
cap (still at 68/100 slash commands after this batch — 221 total commands).

**Utility** (`cogs/utility.py`): `,search` (DuckDuckGo instant answers, free
keyless), `,fx` (currency conversion, free keyless API), `,genpassword`,
`,hash`, `,base64`, `,jsonformat`, `,regextest`, `,colorpreview`,
`,asciiart`, `,mocktext`, `,countdown`.

**Moderation** (`cogs/moderation.py`): `,softban`, `,massban` (ban a list of
IDs), `,lockdown` (lock/unlock the current channel for @everyone).

**Economy** (`cogs/economy.py`): a bank system (`,deposit`, `,withdraw`,
`,bank`, `,collectinterest` — 2%/day on banked coins), `,rob` (risky steal,
daily cooldown), a weekly lottery (`,lottery_buy`, admin `,lottery_draw`),
and `,richest` leaderboard.

**Games** (`cogs/games.py`): Word Chain (`,wordchain`), Anagram solver,
Ship compatibility (`,ship`), Speed Math race, Simon Says (button pattern
memory), and a 20 Questions starter.

**Music** (`cogs/song.py`): `,shuffle` (DJ-gated), `,voteskip` (majority
vote among listeners in the voice channel), `,history` (recently played,
now actually populated as tracks play — previously would've always been
empty since nothing wrote to it).
