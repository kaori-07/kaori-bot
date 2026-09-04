import discord
from discord.ext import commands, tasks
from discord import app_commands, ui
import json
import random
import datetime
import asyncio
from typing import Optional
import pytz
import os
from cogs.utils.emoji_manager import EMOJI

IST = pytz.timezone('Asia/Kolkata')
DATA_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data")
os.makedirs(DATA_DIR, exist_ok=True)
GWY_FILE = os.path.join(DATA_DIR, "gwy.json")

if not os.path.exists(GWY_FILE):
    with open(GWY_FILE, "w") as f:
        json.dump({}, f)

class RerollButton(ui.Button):
    def __init__(self, message_id: str, giveaway_data: dict):
        super().__init__(label=f"{EMOJI['repeat']} Reroll", style=discord.ButtonStyle.red, custom_id="reroll_button")
        self.message_id = message_id
        self.giveaway_data = giveaway_data

    async def callback(self, interaction: discord.Interaction):
        if not interaction.user.guild_permissions.administrator:
            return await interaction.response.send_message("Only admins can reroll giveaways.", ephemeral=True)

        participants = self.giveaway_data.get("participants", [])
        winner_count = self.giveaway_data.get("winner_count", 1)
        prize = self.giveaway_data.get("prize", "Unknown Prize")

        if not participants:
            return await interaction.response.send_message("No valid participants to reroll!", ephemeral=True)

        winners = random.sample(participants, min(len(participants), winner_count))
        mentions = [f"<@{uid}>" for uid in winners]

        embed = discord.Embed(
            title=f"{EMOJI['repeat']} Giveaway Rerolled!",
            description=f"**Prize:** {prize}\n**New Winner(s):** {', '.join(mentions)}",
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"Rerolled by {interaction.user.display_name}")

        await interaction.channel.send(embed=embed)

        for winner in winners:
            try:
                user = await interaction.client.fetch_user(int(winner))
                await user.send(f"{EMOJI['repeat']} You've been rerolled as a new winner for **{prize}** in **{interaction.guild.name}**!")
            except:
                pass

        await interaction.response.send_message("Rerolled successfully!", ephemeral=True)

class GiveawayButton(ui.View):
    def __init__(self, message_id: int, ended: bool = False, giveaway_data: dict = None):
        super().__init__(timeout=None)
        self.message_id = str(message_id)
        self.ended = ended
        self.giveaway_data = giveaway_data or {}

        if self.ended:
            self.add_item(RerollButton(self.message_id, self.giveaway_data))

    @ui.button(label=f"{EMOJI['party']} Join", style=discord.ButtonStyle.green, custom_id="join_giveaway")
    async def join_button(self, interaction: discord.Interaction, button: ui.Button):
        if self.ended:
            return await interaction.response.send_message("This giveaway has already ended.", ephemeral=True)

        with open(GWY_FILE, "r") as f:
            data = json.load(f)

        if self.message_id not in data:
            return await interaction.response.send_message("Giveaway not found.", ephemeral=True)

        if str(interaction.user.id) in data[self.message_id]["banned"]:
            return await interaction.response.send_message("You're banned from joining giveaways.", ephemeral=True)

        if str(interaction.user.id) in data[self.message_id]["participants"]:
            return await interaction.response.send_message("You have already joined!", ephemeral=True)

        data[self.message_id]["participants"].append(str(interaction.user.id))

        with open(GWY_FILE, "w") as f:
            json.dump(data, f, indent=4)

        await interaction.response.send_message(f"You've joined the giveaway! {EMOJI['party']}", ephemeral=True)

    @ui.button(label=f"{EMOJI['users']} Participants", style=discord.ButtonStyle.blurple, custom_id="view_participants")
    async def view_button(self, interaction: discord.Interaction, button: ui.Button):
        with open(GWY_FILE, "r") as f:
            data = json.load(f)

        if self.message_id not in data:
            return await interaction.response.send_message("Giveaway not found.", ephemeral=True)

        participants = data[self.message_id]["participants"]
        member_list = [f"<@{user_id}>" for user_id in participants]

        embed = discord.Embed(title=f"{EMOJI['ticket_alt']} Participants", description="\n".join(member_list) or "No participants yet!", color=discord.Color.blurple())
        await interaction.response.send_message(embed=embed, ephemeral=True)

class Giveaway(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.check_giveaways.start()

    def cog_unload(self):
        self.check_giveaways.cancel()

    @tasks.loop(seconds=60)
    async def check_giveaways(self):
        with open(GWY_FILE, "r") as f:
            data = json.load(f)

        now = datetime.datetime.now(IST).timestamp()
        to_remove = []

        for msg_id, details in data.items():
            if now >= details["end_timestamp"]:
                guild = self.bot.get_guild(details["guild_id"])
                if not guild:
                    continue
                channel = guild.get_channel(details["channel_id"])
                if not channel:
                    continue
                try:
                    message = await channel.fetch_message(int(msg_id))
                except:
                    continue

                participants = details["participants"]
                winners_count = details["winner_count"]
                winners = random.sample(participants, min(len(participants), winners_count)) if participants else []

                winner_mentions = [f"<@{uid}>" for uid in winners] if winners else ["No valid entries"]
                host = f"<@{details['host_id']}>"

                embed = discord.Embed(
                    title=f"{EMOJI['party']} Giveaway Ended!",
                    description=f"**Prize:** {details['prize']}",
                    color=discord.Color.gold()
                )
                embed.add_field(name=f"{EMOJI['trophy']} Winner(s)", value="\n".join(winner_mentions), inline=False)
                embed.add_field(name=f"{EMOJI['user']} Hosted by", value=host, inline=True)
                embed.set_footer(text=f"Giveaway ended {EMOJI['gift']}")
                embed.set_thumbnail(url=guild.icon.url if guild.icon else discord.Embed.Empty)

                await message.edit(embed=embed, view=GiveawayButton(int(msg_id), ended=True, giveaway_data=details))
                await channel.send(f"{EMOJI['confetti']} Congratulations {', '.join(winner_mentions)}! You won **{details['prize']}**!")

                for winner in winners:
                    try:
                        user = await self.bot.fetch_user(int(winner))
                        await user.send(f"{EMOJI['party']} You won **{details['prize']}** in **{guild.name}**!\n[Jump to Giveaway](https://discord.com/channels/{guild.id}/{channel.id}/{msg_id})")
                    except:
                        pass

                to_remove.append(msg_id)

        for msg_id in to_remove:
            data.pop(msg_id)

        with open(GWY_FILE, "w") as f:
            json.dump(data, f, indent=4)

    @commands.hybrid_command(name="gstart", description="Start a giveaway")
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def gstart(self, ctx: commands.Context, duration: str, winners: int, *, prize: str):
        if not ctx.author.guild_permissions.administrator:
            return await ctx.reply("You must be an admin to start giveaways.")

        unit = duration[-1]
        if unit not in ['s', 'm', 'h', 'd']:
            return await ctx.reply("Invalid duration format. Use s/m/h/d")

        try:
            amount = int(duration[:-1])
        except:
            return await ctx.reply("Invalid duration amount.")

        seconds = {'s': 1, 'm': 60, 'h': 3600, 'd': 86400}[unit] * amount
        end_time = datetime.datetime.now(IST) + datetime.timedelta(seconds=seconds)

        embed = discord.Embed(title=f"{EMOJI['party']} GIVEAWAY {EMOJI['party']}", description=f"**Prize:** {prize}\n**Hosted by:** <@{ctx.author.id}>", color=discord.Color.green())
        embed.add_field(name="Ends at", value=f"<t:{int(end_time.timestamp())}:F>", inline=False)
        embed.set_thumbnail(url=ctx.guild.icon.url if ctx.guild.icon else discord.Embed.Empty)

        msg = await ctx.channel.send(embed=embed, view=GiveawayButton(message_id=0))

        with open(GWY_FILE, "r") as f:
            data = json.load(f)

        data[str(msg.id)] = {
            "channel_id": ctx.channel.id,
            "guild_id": ctx.guild.id,
            "host_id": ctx.author.id,
            "end_timestamp": int(end_time.timestamp()),
            "winner_count": winners,
            "prize": prize,
            "participants": [],
            "banned": []
        }

        with open(GWY_FILE, "w") as f:
            json.dump(data, f, indent=4)

        await msg.edit(view=GiveawayButton(message_id=msg.id))
        await ctx.reply("Giveaway started!", ephemeral=True if isinstance(ctx, discord.Interaction) else False)

    @commands.hybrid_command(name="gend", description="End a giveaway early")
    @commands.guild_only()
    @app_commands.allowed_installs(guilds=True, users=False)
    @app_commands.allowed_contexts(guilds=True, dms=False, private_channels=False)
    async def gend(self, ctx: commands.Context, message_id: str):
        if not ctx.author.guild_permissions.administrator:
            return await ctx.reply(f"{EMOJI['error']} You must be an admin to end giveaways.")

        with open(GWY_FILE, "r") as f:
            data = json.load(f)

        if message_id not in data:
            return await ctx.reply(f"{EMOJI['error']} Giveaway not found.")

        data[message_id]["end_timestamp"] = datetime.datetime.now(IST).timestamp()

        with open(GWY_FILE, "w") as f:
            json.dump(data, f, indent=4)

        await ctx.reply(f"{EMOJI['success']} Giveaway will end shortly.")

    @commands.command(name="reroll", description="Reroll giveaway winner")
    @commands.guild_only()
    async def reroll(self, ctx: commands.Context, message_id: str):
        if not ctx.author.guild_permissions.administrator:
            return await ctx.reply("You must be an admin to reroll giveaways.")

        with open(GWY_FILE, "r") as f:
            data = json.load(f)

        if message_id not in data:
            return await ctx.reply("Giveaway not found.")

        details = data[message_id]
        participants = details["participants"]
        winners = random.sample(participants, min(len(participants), details["winner_count"])) if participants else []
        mentions = [f"<@{uid}>" for uid in winners] if winners else ["No valid entries"]

        embed = discord.Embed(
            title=f"{EMOJI['repeat']} Giveaway Rerolled!",
            description=f"**Prize:** {details['prize']}\n**New Winner(s):** {', '.join(mentions)}",
            color=discord.Color.purple()
        )
        embed.set_footer(text=f"Rerolled by {ctx.author.display_name}")

        await ctx.send(embed=embed)

        for winner in winners:
            try:
                user = await self.bot.fetch_user(int(winner))
                await user.send(f"{EMOJI['repeat']} You've been rerolled as a new winner for **{details['prize']}** in **{ctx.guild.name}**!")
            except:
                continue

    @commands.command(name="gban", description="Ban a user from giveaways")
    @commands.guild_only()
    async def gban(self, ctx: commands.Context, user: discord.User):
        if not ctx.author.guild_permissions.administrator:
            return await ctx.reply(f"{EMOJI['error']} Only admins can ban users from giveaways.")

        with open(GWY_FILE, "r") as f:
            data = json.load(f)

        for entry in data.values():
            if str(user.id) not in entry["banned"]:
                entry["banned"].append(str(user.id))

        with open(GWY_FILE, "w") as f:
            json.dump(data, f, indent=4)

        await ctx.reply(f"{EMOJI['boot_kick']} {user.mention} is now banned from giveaways.")

    @commands.command(name="gbanlist", description="List banned users")
    @commands.guild_only()
    async def gbanlist(self, ctx: commands.Context):
        with open(GWY_FILE, "r") as f:
            data = json.load(f)

        banned_ids = set()
        for entry in data.values():
            banned_ids.update(entry['banned'])

        if not banned_ids:
            return await ctx.reply(f"{EMOJI['info']} No users banned from giveaways.")

        mentions = [f"<@{uid}>" for uid in banned_ids]
        embed = discord.Embed(title=f"{EMOJI['forbidden']} Giveaway Banned Users", description="\n".join(mentions), color=discord.Color.red())
        await ctx.reply(embed=embed)

async def setup(bot):
    await bot.add_cog(Giveaway(bot))
