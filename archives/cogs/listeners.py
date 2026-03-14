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

        leveling_cog = self.bot.get_cog('Leveling')
        analytics_cog = self.bot.get_cog('Analytics')
        sticky_cog = self.bot.get_cog('Sticky')

        if leveling_cog:
            await leveling_cog.process_message_for_leveling(message)

        if analytics_cog:
            await analytics_cog.process_message_for_analytics(message)

        if sticky_cog:
            await sticky_cog.on_message(message)

        await self.bot.process_commands(message)  # So commands still work

    @commands.Cog.listener()
    async def on_presence_update(self, before, after):
        guild = discord.utils.get(self.bot.guilds, id=1071601574616498248)
        if not guild or before.id not in [m.id for m in guild.members]:
            return


        analytics_cog = self.bot.get_cog('Analytics')

        if analytics_cog:
            await analytics_cog.process_status_change(before, after)

    @commands.Cog.listener()
    async def on_reaction_add(self, reaction: Reaction, user: Member):  # <-- fixed here
        if user.bot or reaction.message.guild.id != 1071601574616498248:
            return
        fireboard_cog = self.bot.get_cog('Fireboard')

        if fireboard_cog:
            await fireboard_cog.fireboard_react_add(reaction, user)  # <-- fixed call

    @commands.Cog.listener()
    async def on_member_remove(self, member: Member):
        if member.bot or member.guild.id != 1071601574616498248:
            return
        # """Log the roles when a member leaves the server."""
        # gid, uid = str(member.guild.id), str(member.id)
        # pr = self.data.setdefault('persisted_roles', {}).setdefault(gid, {})
        # lst = pr.setdefault(uid, [])
        
        # # Save current roles to the persisted roles list
        # current_roles = [role.id for role in member.roles if role.id in lst]
        # pr[uid] = current_roles
        # self.data.save_data()  # Assuming save_data is a method of your data handler
        # print(f"Logged persistent roles for {member.name} when they left: {current_roles}")

        logging_cog = self.bot.get_cog('Logging')

        if logging_cog:
            await logging_cog.on_member_remove(member)

    @commands.Cog.listener()
    async def on_member_join(self, member: Member):
        if member.bot or member.guild.id != 1071601574616498248:
            return

        # """Reassign persistent roles when a member rejoins the server."""
        # gid, uid = str(member.guild.id), str(member.id)
        # pr = self.data.get('persisted_roles', {}).get(gid, {})
        
        # # Check if the member had persistent roles saved
        # persistent_roles = pr.get(uid, [])
        
        # # Reassign any roles that were marked as persistent
        # for role_id in persistent_roles:
        #     role = discord.utils.get(member.guild.roles, id=role_id)
        #     if role:
        #         await member.add_roles(role)
        #         print(f"Reassigned persistent role {role.name} to {member.name}.")

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
    async def image_message_delete(self, message):
        if message.author.bot or message.guild.id != 1071601574616498248:
            return

        logging_cog = self.bot.get_cog('Logging')

        if logging_cog:
            await logging_cog.image_message_delete(message)

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
    async def on_guild_emoji_create(self, emoji):
        logging_cog = self.bot.get_cog('Logging')

        if logging_cog:
            await logging_cog.on_guild_emoji_create(emoji)

    @commands.Cog.listener()
    async def on_guild_emoji_delete(self, emoji):
        logging_cog = self.bot.get_cog('Logging')

        if logging_cog:
            await logging_cog.on_guild_emoji_delete(emoji)

    @commands.Cog.listener()
    async def on_voice_state_update(self, member, before, after):
        logging_cog = self.bot.get_cog('Logging')

        if logging_cog:
            await logging_cog.on_voice_state_update(member, before, after)

    @commands.Cog.listener()
    async def on_guild_channel_update(self, before, after):
        logging_cog = self.bot.get_cog('Logging')

        if logging_cog:
            await logging_cog.on_guild_channel_update(before, after)

async def setup(bot):
    await bot.add_cog(Listeners(bot))
