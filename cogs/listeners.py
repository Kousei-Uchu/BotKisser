from discord import Member, Reaction
from discord.ext import commands
import discord


class Listeners(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

    @commands.Cog.listener()
    async def on_message(self, message):
        if message.author.bot or message.guild.id != 1071601574616498248:
            return

        leveling_cog  = self.bot.get_cog('Leveling')
        analytics_cog = self.bot.get_cog('Analytics')
        sticky_cog    = self.bot.get_cog('Sticky')

        if leveling_cog:
            await leveling_cog.process_message_for_leveling(message)

        if analytics_cog:
            await analytics_cog.process_message_for_analytics(message)

        if sticky_cog:
            await sticky_cog.on_message(message)

        await self.bot.process_commands(message)

    @commands.Cog.listener()
    async def on_presence_update(self, before, after):
        guild = discord.utils.get(self.bot.guilds, id=1071601574616498248)
        # Use get_member() instead of building a full member list every event
        if not guild or not guild.get_member(before.id):
            return

        analytics_cog = self.bot.get_cog('Analytics')
        if analytics_cog:
            await analytics_cog.process_status_change(before, after)

    # NOTE: Fireboard's on_reaction_add listener fires directly from the Fireboard
    # cog — no need to proxy it here.  The old call to fireboard_react_add() was
    # referencing a method that doesn't exist and has been removed.

    @commands.Cog.listener()
    async def on_member_remove(self, member: Member):
        if member.bot or member.guild.id != 1071601574616498248:
            return

        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            await logging_cog.on_member_remove(member)

    @commands.Cog.listener()
    async def on_member_join(self, member: Member):
        if member.bot or member.guild.id != 1071601574616498248:
            return

        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            await logging_cog.on_member_join(member)

    @commands.Cog.listener()
    async def on_ready(self):
        sticky_cog = self.bot.get_cog('Sticky')
        if sticky_cog:
            await sticky_cog.sticky_on_ready()

    @commands.Cog.listener()
    async def on_message_delete(self, message):
        if message.author.bot or message.guild.id != 1071601574616498248:
            return

        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            await logging_cog.message_delete(message)
            # Also handle image deletions within the same event
            if message.attachments:
                await logging_cog.image_message_delete(message)

    @commands.Cog.listener()
    async def on_message_edit(self, before, after):
        if before.author.bot or before.guild.id != 1071601574616498248:
            return

        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            await logging_cog.message_edit(before, after)

    @commands.Cog.listener()
    async def on_bulk_message_delete(self, messages):
        if all(m.author.bot or m.guild.id != 1071601574616498248 for m in messages):
            return

        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            await logging_cog.bulk_message_delete(messages)

    @commands.Cog.listener()
    async def on_member_update(self, before, after):
        if before.bot or before.guild.id != 1071601574616498248:
            return

        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            await logging_cog.on_member_update(before, after)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            await logging_cog.on_member_ban(guild, user)

    @commands.Cog.listener()
    async def on_member_unban(self, guild, user):
        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            await logging_cog.on_member_unban(guild, user)

    @commands.Cog.listener()
    async def on_guild_role_create(self, role):
        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            await logging_cog.on_guild_role_create(role)

    @commands.Cog.listener()
    async def on_guild_role_delete(self, role):
        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            await logging_cog.on_guild_role_delete(role)

    @commands.Cog.listener()
    async def on_guild_role_update(self, before, after):
        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            await logging_cog.on_guild_role_update(before, after)

    @commands.Cog.listener()
    async def on_guild_channel_create(self, channel):
        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            await logging_cog.on_guild_channel_create(channel)

    @commands.Cog.listener()
    async def on_guild_channel_delete(self, channel):
        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            await logging_cog.on_guild_channel_delete(channel)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        logging_cog = self.bot.get_cog('Logging')
        if logging_cog:
            await logging_cog.on_guild_channel_update(before, after)


async def setup(bot):
    await bot.add_cog(Listeners(bot))