import discord
from discord.ext import commands

from utils.db_handlers.fireboard_db import FireboardDB
from utils.config_manager import ConfigManager


class Fireboard(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.db = FireboardDB()

        config = ConfigManager("config.json").load_config()
        self.config = config.get("fireboard", {})

        self.channel_id = self.config.get("channel_id")

        self.reactions = self.config.get("reactions", {
            "🔥": 5
        })

    def build_embeds(self, message, count, emoji):
        embeds = []

        main = discord.Embed(
            title=f"{emoji} {count}",
            description=message.content or "*No content*",
            color=discord.Color.orange()
        )

        main.set_author(
            name=str(message.author),
            icon_url=message.author.display_avatar.url
        )

        main.add_field(
            name="Jump",
            value=f"[Click Here]({message.jump_url})",
            inline=False
        )

        main.set_footer(text=f"#{message.channel.name}")

        if message.attachments:
            main.set_image(url=message.attachments[0].url)

        embeds.append(main)

        for att in message.attachments[1:]:
            e = discord.Embed(color=discord.Color.orange())
            e.set_image(url=att.url)
            embeds.append(e)

        return embeds

    async def count_reactors(self, message, emoji):
        users = set()

        for react in message.reactions:
            if str(react.emoji) == emoji:
                async for u in react.users():
                    if not u.bot and u.id != message.author.id:
                        users.add(u.id)

        return users

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction, user):
        if user.bot:
            return

        emoji = str(reaction.emoji)

        if emoji not in self.reactions:
            return

        message = reaction.message

        threshold = self.reactions[emoji]

        fireboard_channel = self.bot.get_channel(self.channel_id)

        if not fireboard_channel:
            return

        users = await self.count_reactors(message, emoji)
        count = len(users)

        record = self.db.get_message(message.id)

        if record:
            board_msg = await fireboard_channel.fetch_message(record["repost_id"])
            embeds = self.build_embeds(message, count, emoji)
            await board_msg.edit(embeds=embeds)

        elif count >= threshold:
            embeds = self.build_embeds(message, count, emoji)
            post = await fireboard_channel.send(embeds=embeds)
            await post.add_reaction(emoji)

            attachments = [a.url for a in message.attachments]

            self.db.save_message(
                message.id,
                post.id,
                message.channel.id,
                emoji,
                attachments
            )

            for uid in users:
                self.db.add_stat(message.id, uid)

    @commands.command()
    async def fireleaderboard(self, ctx):
        data = self.db.get_leaderboard()

        embed = discord.Embed(
            title="🔥 Fireboard Leaderboard",
            color=discord.Color.orange()
        )

        for i, row in enumerate(data, 1):
            user = self.bot.get_user(row["user_id"])
            name = user.name if user else f"User {row['user_id']}"

            embed.add_field(
                name=f"#{i} {name}",
                value=f"{row['fires']} fires",
                inline=False
            )

        await ctx.send(embed=embed)


async def setup(bot):
    await bot.add_cog(Fireboard(bot))