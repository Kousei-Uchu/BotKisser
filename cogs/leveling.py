import discord
from discord.ext import commands
from discord import app_commands, Embed
from utils.db_handlers.leveling_db import LevelingDB
from utils.config_manager import ConfigManager
import random

class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = LevelingDB()
        self.config = ConfigManager('config.json').load_config().get('leveling', {})

    # -------------------------
    # Permission check helper
    # -------------------------
    def has_permission(self, interaction: discord.Interaction, command: str) -> bool:
        cfg = self.config.get("commands", {}).get(command, {})
        if not cfg.get("enabled", True):
            return False
        required_roles = set(cfg.get("required_roles", []))
        required_perms = cfg.get("permissions", [])

        if required_roles and "@everyone" not in required_roles:
            user_roles = {str(r.id) for r in interaction.user.roles} | {r.name for r in interaction.user.roles}
            if not user_roles & required_roles:
                return False

        perms = interaction.channel.permissions_for(interaction.user)
        return all(getattr(perms, p, False) for p in required_perms)

    # -------------------------
    # Level calculation
    # -------------------------
    def calculate_xp_needed(self, level: int) -> int:
        return 75 + 100 * (level - 1)

    # -------------------------
    # Add XP and handle level up
    # -------------------------
    async def process_message_for_leveling(self, message: discord.Message):
        if message.author.bot or not self.config.get('enabled', True):
            return

        xp_cfg = self.config.get("xp_gain", {})
        if not xp_cfg.get("enabled", True):
            return

        xp = random.randint(xp_cfg.get("min_xp", 10), xp_cfg.get("max_xp", 20))
        level_up, new_level = await self.update_user_level(message.author.id, message.guild.id, xp)

        # Level up notification
        if level_up and self.config.get("level_up", {}).get("enabled", True):
            msg_template = self.config["level_up"].get("message", "{user} leveled up to {level}!")
            ch_id = self.config["level_up"].get("channel_id")
            channel = self.bot.get_channel(int(ch_id)) if ch_id else message.channel
            await channel.send(msg_template.format(user=message.author.mention, level=new_level))

            # Assign level role if configured
            roles_cfg = self.config.get("level_roles", {})
            role_id = roles_cfg.get(str(new_level))
            if role_id:
                role = message.guild.get_role(int(role_id))
                if role:
                    await message.author.add_roles(role)

    async def update_user_level(self, user_id: int, guild_id: int, xp_to_add: int = 0):
        """Adds XP and calculates level up using SQL backend"""
        data = await self.db.get_user(guild_id, user_id)
        if not data:
            level = 1
            xp = 0
            await self.db.create_user(guild_id, user_id)
        else:
            level = data['level']
            xp = data['xp']

        xp += xp_to_add
        leveled_up = False

        while xp >= (needed := self.calculate_xp_needed(level)):
            xp -= needed
            level += 1
            leveled_up = True

        await self.db.set_user(guild_id, user_id, xp, level)
        return leveled_up, level

    # -------------------------
    # Commands
    # -------------------------
    @app_commands.command(name="level", description="Check the level and XP of a user.")
    async def level(self, interaction: discord.Interaction, member: discord.Member = None):
        if not self.has_permission(interaction, "level"):
            return await interaction.response.send_message("You do not have permission.", ephemeral=True)

        member = member or interaction.user
        data = await self.db.get_user(interaction.guild.id, member.id)
        if not data:
            return await interaction.response.send_message(f"{member.display_name} hasn't earned XP yet!", ephemeral=True)

        level = data['level']
        xp = data['xp']
        xp_needed = self.calculate_xp_needed(level)
        progress = (xp / xp_needed) * 100

        embed = Embed(title=f"{member.display_name}'s Level Stats", color=discord.Color.green())
        embed.add_field(name="Level", value=str(level))
        embed.add_field(name="XP", value=f"{xp} / {xp_needed}")
        embed.add_field(name="Progress", value=f"{progress:.1f}%")
        embed.set_thumbnail(url=member.display_avatar.url)

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="leaderboard", description="Check the server's leaderboard.")
    async def leaderboard(self, interaction: discord.Interaction):
        if not self.has_permission(interaction, "level"):
            return await interaction.response.send_message("You do not have permission.", ephemeral=True)

        top = await self.db.get_leaderboard(interaction.guild.id, limit=10)
        if not top:
            return await interaction.response.send_message("No data found.", ephemeral=True)

        embed = Embed(title=f"{interaction.guild.name} Leaderboard", color=discord.Color.gold())
        for i, row in enumerate(top, start=1):
            member = interaction.guild.get_member(int(row['user_id']))
            name = member.display_name if member else f"<@{row['user_id']}>"
            embed.add_field(name=f"{i}. {name}", value=f"Level {row['level']} ({row['xp']} XP)", inline=False)

        await interaction.response.send_message(embed=embed)

    # -------------------------
    # Admin Commands
    # -------------------------
    @app_commands.command(name="setlevel", description="Set a user's level.")
    async def setlevel(self, interaction: discord.Interaction, member: discord.Member, level: int):
        if not self.has_permission(interaction, "setlevel"):
            return await interaction.response.send_message("You do not have permission.", ephemeral=True)
        if level < 1:
            return await interaction.response.send_message("Level must be at least 1.", ephemeral=True)

        await self.db.set_user(interaction.guild.id, member.id, xp=0, level=level)
        await interaction.response.send_message(f"Set {member.mention}'s level to {level}.")

    @app_commands.command(name="addxp", description="Add XP to a user.")
    async def addxp(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if not self.has_permission(interaction, "addxp"):
            return await interaction.response.send_message("You do not have permission.", ephemeral=True)
        await self.update_user_level(member.id, interaction.guild.id, amount)
        await interaction.response.send_message(f"Gave {amount} XP to {member.mention}.")

    @app_commands.command(name="removexp", description="Remove XP from a user.")
    async def removexp(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if not self.has_permission(interaction, "removexp"):
            return await interaction.response.send_message("You do not have permission.", ephemeral=True)
        await self.update_user_level(member.id, interaction.guild.id, -amount)
        await interaction.response.send_message(f"Removed {amount} XP from {member.mention}.")

    @app_commands.command(name="grantlevel", description="Grant levels to a user.")
    async def grantlevel(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if not self.has_permission(interaction, "grantlevel"):
            return await interaction.response.send_message("You do not have permission.", ephemeral=True)
        data = await self.db.get_user(interaction.guild.id, member.id)
        level = data['level'] if data else 1
        new_level = level + amount
        await self.db.set_user(interaction.guild.id, member.id, xp=0, level=new_level)
        await interaction.response.send_message(f"Granted {amount} levels to {member.mention}.")

    @app_commands.command(name="revokelevel", description="Revoke levels from a user.")
    async def revokelevel(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if not self.has_permission(interaction, "revokelevel"):
            return await interaction.response.send_message("You do not have permission.", ephemeral=True)
        data = await self.db.get_user(interaction.guild.id, member.id)
        if not data:
            return await interaction.response.send_message("User data not found.", ephemeral=True)
        new_level = max(1, data['level'] - amount)
        await self.db.set_user(interaction.guild.id, member.id, xp=0, level=new_level)
        await interaction.response.send_message(f"Revoked {amount} levels from {member.mention}.")

async def setup(bot):
    await bot.add_cog(Leveling(bot))