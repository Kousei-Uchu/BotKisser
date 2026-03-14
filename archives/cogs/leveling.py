import os
import tempfile
import time
import uuid
import discord
from discord.ext import commands
from discord import File, app_commands
import random
from html2image import Html2Image
from utils.data_handler import DataHandler
from utils.config_manager import ConfigManager

class Leveling(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_handler = DataHandler('data/leveling.json')
        self.config = ConfigManager('config.json').load_config().get('leveling', {})

    def calculate_xp_needed(self, level):
        return 75 + 100 * (level - 1)

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

    async def update_user_level(self, user_id, guild_id, xp_to_add=0):
        guild_id, user_id = str(guild_id), str(user_id)
        data = self.data_handler.load_data()
        user_data = data.setdefault(guild_id, {}).setdefault(user_id, {'xp': 0, 'level': 1})

        user_data['xp'] += xp_to_add
        level_up = False

        while user_data['xp'] >= (needed := self.calculate_xp_needed(user_data['level'])):
            user_data['level'] += 1
            user_data['xp'] -= needed
            level_up = True

        self.data_handler.save_data(data)
        return level_up, user_data['level']

    async def process_message_for_leveling(self, message):
        if message.author.bot or not self.config.get('enabled', True):
            return

        xp_cfg = self.config.get("xp_gain", {})
        if not xp_cfg.get("enabled", True):
            return

        xp = random.randint(xp_cfg.get("min_xp", 10), xp_cfg.get("max_xp", 20))
        level_up, level = await self.update_user_level(message.author.id, message.guild.id, xp)

        if level_up and self.config.get("level_up", {}).get("enabled", True):
            msg_template = self.config["level_up"].get("message", "{user} leveled up to {level}!")
            ch_id = self.config["level_up"].get("channel_id")
            channel = self.bot.get_channel(int(ch_id)) if ch_id else message.channel
            await channel.send(msg_template.format(user=message.author.mention, level=level))

            roles = self.config.get("level_roles", {})
            if str(level) in roles:
                role = message.guild.get_role(int(roles[str(level)]))
                if role:
                    await message.author.add_roles(role)

    import tempfile

    def render_html_to_image(self, html: str, filename_prefix: str) -> str:
        output_dir = "C:\\Users\\amacc\\OneDrive\\Documents\\The-Den-Bot\\data"
        hti = Html2Image(output_path=output_dir)

        # Save HTML to a temporary file
        with tempfile.NamedTemporaryFile("w", delete=False, suffix=".html") as tmpfile:
            tmpfile.write(html)
            tmp_html_path = tmpfile.name

        filename = f"{filename_prefix}-{uuid.uuid4().hex}.png"
        full_path = os.path.join(output_dir, filename)

        # Take screenshot of the temp HTML file
        hti.screenshot(html_file=tmp_html_path, save_as=filename)

        time.sleep(1)

        # Delete temp HTML file after screenshot is done
        os.remove(tmp_html_path)

        return full_path


    @app_commands.command(name="level", description="Check the level and XP of a user.")
    async def level(self, interaction: discord.Interaction, member: discord.Member = None):
        if not self.has_permission(interaction, "level"):
            return await interaction.response.send_message("You do not have permission.")

        member = member or interaction.user
        data = self.data_handler.load_data().get(str(interaction.guild.id), {}).get(str(member.id))
        if not data:
            return await interaction.response.send_message(f"{member.display_name} hasn't earned XP yet!")

        level, xp = data['level'], data['xp']
        xp_needed = self.calculate_xp_needed(level)
        progress = (xp / xp_needed) * 100

        html = f"""
            <!DOCTYPE html>
            <html lang="en">
            <head>
            <meta charset="UTF-8" />
            <meta name="viewport" content="width=device-width, initial-scale=1" />
            <title>Level Stats</title>
            <style>
            body {{
                background-color: #1f1f1f;
                color: #2ecc71;
                font-family: Arial, sans-serif;
                padding: 15px;
                border: 1px solid #2ecc71;
                border-radius: 10px;
                margin: 0;
            }}
            h2 {{
                margin-bottom: 10px;
            }}
            p {{
                margin: 5px 0;
            }}
            </style>
            </head>
            <body>
            <h2>{member.display_name}'s Level Stats</h2>
            <p><strong>Level:</strong> {level}</p>
            <p><strong>XP:</strong> {xp} / {xp_needed}</p>
            <p><strong>Progress:</strong> {progress:.1f}%</p>
            </body>
            </html>
            """
        image_path = self.render_html_to_image(html, "level")
        await interaction.response.send_message(file=File(image_path))
        os.remove(image_path)

    @app_commands.command(name="leaderboard", description="Check the server's leaderboard.")
    async def leaderboard(self, interaction: discord.Interaction):
        if not self.has_permission(interaction, "level"):
            return await interaction.response.send_message("You do not have permission.")

        data = self.data_handler.load_data().get(str(interaction.guild.id), {})
        if not data:
            return await interaction.response.send_message("No data found.")

        top = sorted(data.items(), key=lambda x: (x[1]['level'], x[1]['xp']), reverse=True)[:10]
        html = """<div style='background: #1f1f1f; padding: 10px; border-radius: 10px;'>
        <h2 style='color: gold;'>Server Leaderboard</h2>
        <ol style='color: white;'>"""
        for uid, stats in top:
            member = interaction.guild.get_member(int(uid))
            name = member.display_name if member else f"<@{uid}>"
            html += f"<li>{name} — Level {stats['level']} ({stats['xp']} XP)</li>"
        html += "</ol></div>"

        image_path = self.render_html_to_image(html, "level")
        with open(image_path, "rb") as f:
            await interaction.response.send_message(file=File(image_path))
        os.remove(image_path)

    @app_commands.command(name="setlevel", description="Set the level of a user.")
    async def setlevel(self, interaction: discord.Interaction, member: discord.Member, level: int):
        if not self.has_permission(interaction, "setlevel"):
            return await interaction.response.send_message("You do not have permission.")
        if level < 1:
            return await interaction.response.send_message("Level must be at least 1.")

        data = self.data_handler.load_data()
        data.setdefault(str(interaction.guild.id), {})[str(member.id)] = {'xp': 0, 'level': level}
        self.data_handler.save_data(data)
        await interaction.response.send_message(f"Set {member.mention}'s level to {level}.")

    @app_commands.command(name="addxp", description="Add XP to a user.")
    async def addxp(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if not self.has_permission(interaction, "addxp"):
            return await interaction.response.send_message("You do not have permission.")
        await self.update_user_level(member.id, interaction.guild.id, amount)
        await interaction.response.send_message(f"Gave {amount} XP to {member.mention}.")

    @app_commands.command(name="removexp", description="Remove XP from a user.")
    async def removexp(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if not self.has_permission(interaction, "removexp"):
            return await interaction.response.send_message("You do not have permission.")
        await self.update_user_level(member.id, interaction.guild.id, -amount)
        await interaction.response.send_message(f"Removed {amount} XP from {member.mention}.")

    @app_commands.command(name="grantlevel", description="Grant levels to a user.")
    async def grantlevel(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if not self.has_permission(interaction, "grantlevel"):
            return await interaction.response.send_message("You do not have permission.")

        data = self.data_handler.load_data()
        entry = data.setdefault(str(interaction.guild.id), {}).setdefault(str(member.id), {'xp': 0, 'level': 1})
        entry['level'] += amount
        self.data_handler.save_data(data)
        await interaction.response.send_message(f"Granted {amount} levels to {member.mention}.")

    @app_commands.command(name="revokelevel", description="Revoke levels from a user.")
    async def revokelevel(self, interaction: discord.Interaction, member: discord.Member, amount: int):
        if not self.has_permission(interaction, "revokelevel"):
            return await interaction.response.send_message("You do not have permission.")

        data = self.data_handler.load_data()
        entry = data.get(str(interaction.guild.id), {}).get(str(member.id))
        if not entry:
            return await interaction.response.send_message("User data not found.")
        entry['level'] = max(1, entry['level'] - amount)
        self.data_handler.save_data(data)
        await interaction.response.send_message(f"Revoked {amount} levels from {member.mention}.")

async def setup(bot):
    await bot.add_cog(Leveling(bot))
