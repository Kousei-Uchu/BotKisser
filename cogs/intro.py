import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import openpyxl
import os
import asyncio

from utils.config_manager import ConfigManager

class IntroSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config_manager = ConfigManager("config.json")
        self.config = self.config_manager.load_config().get("intro", {})

        self.workbook = None
        self.worksheet = None
        self.excel_path = self.config.get("excel_file_path", "responses.xlsx")

        # Command permission defaults
        self.command_configs = {
            "intro": {"enabled": True, "required_roles": ["@everyone"], "permissions": []},
            "refresh_intros": {"enabled": True, "required_roles": ["@everyone"], "permissions": []}
        }
        self.update_command_configs()

    # ==================== Command Permissions ====================
    def update_command_configs(self):
        if "commands" in self.config:
            for cmd, cfg in self.config["commands"].items():
                if cmd in self.command_configs:
                    self.command_configs[cmd].update(cfg)

    async def check_command_permissions(self, interaction: discord.Interaction, command_name: str):
        if command_name not in self.command_configs:
            return False
        cfg = self.command_configs[command_name]
        if not cfg.get("enabled", True):
            return False

        # Guild permissions
        for perm in cfg.get("permissions", []):
            if not getattr(interaction.user.guild_permissions, perm, False):
                return False

        # Roles
        required_roles = cfg.get("required_roles", [])
        if required_roles and "@everyone" not in required_roles:
            user_roles = [str(role.id) for role in interaction.user.roles]
            if not any(r in user_roles for r in required_roles):
                return False

        return True

    # ==================== Excel Handling ====================
    async def init_excel(self):
        if self.workbook and self.worksheet:
            return
        if not os.path.exists(self.excel_path):
            print(f"[init_excel] Excel file not found: {self.excel_path}")
            return

        def load_excel():
            wb = openpyxl.load_workbook(self.excel_path)
            ws = wb["Responses"] or wb.active
            return wb, ws

        try:
            self.workbook, self.worksheet = await asyncio.to_thread(load_excel)
        except Exception as e:
            print(f"[init_excel] Failed to load Excel: {e}")

    async def get_all_records(self):
        await self.init_excel()
        if not self.worksheet:
            return []
        def fetch_rows():
            rows = list(self.worksheet.iter_rows(values_only=True))
            if not rows:
                return []
            headers = rows[0]
            return [dict(zip(headers, row)) for row in rows[1:]]
        return await asyncio.to_thread(fetch_rows)

    # ==================== Age Handling ====================
    def calculate_age(self, birth_year_or_age):
        current_year = datetime.now().year
        try:
            val = int(birth_year_or_age)
            if 1900 <= val <= current_year:
                return current_year - val
            if 8 <= val <= 100:
                return val
        except Exception:
            pass
        return None

    def get_age_bracket(self, age):
        if age < 16: return "13-15"
        if age < 18: return "16-17"
        if age < 21: return "18-20"
        if age < 31: return "21-30"
        if age < 41: return "31-40"
        return "40+"
        
    async def on_member_join(self, member):
        print(f"[on_member_join] Member joined: {member}")
        if not self.config.get('enabled', True):
            print("[on_member_join] Intro system is disabled.")
            return
        self.init_excel()
        if not self.worksheet:
            print("[on_member_join] Worksheet not loaded.")
            return
        await self.process_intro(member)
        message_content = f"**Welcome to The Den {member.mention}! We're so glad to have you!**\n\n<@&1296350497929695232> come say hi! Some more info about them is in <#1071601575744766038>!"
        channel_id = 1071601576252289158
        channel = self.bot.get_channel(channel_id)
        await channel.send(content=message_content)

    # ==================== Intro Processing ====================
    async def process_intro(self, member: discord.Member, row_num: int = None):
        records = await self.get_all_records()
        if not records:
            print("[process_intro] No records found.")
            return

        # Match record
        user_record = None
        if row_num is not None and 1 <= row_num <= len(records):
            user_record = records[row_num - 1]
        else:
            for record in reversed(records):
                username_match = str(record.get("Username", "")).lower() == str(member).lower()
                preferred_name_match = str(record.get("What's your preferred name?", "")).lower() == str(member.name).lower()
                if username_match or preferred_name_match:
                    user_record = record
                    break

        if not user_record:
            print(f"[process_intro] No record found for {member}")
            return

        channel_id = self.config.get("channel_id")
        if not channel_id:
            print("[process_intro] No intro channel ID set.")
            return
        channel = self.bot.get_channel(channel_id)
        if not channel:
            print(f"[process_intro] Intro channel not found: {channel_id}")
            return

        embed = discord.Embed(title="Get to know me!", color=discord.Color.blue())

        # Include all non-empty fields from Excel except skipped
        for key, value in user_record.items():
            if value and str(value).lower() not in ["", "n/a", "skipped"] and key not in ["Discovery Source", "Age", "Birthday", "Join Goals", "Username"]:
                embed.add_field(name=key, value=value, inline=False)

        # Age roles
        age_input = user_record.get("Age", "")
        if age_input:
            age = self.calculate_age(age_input)
            if age is not None:
                age_bracket = self.get_age_bracket(age)
                age_roles = self.config.get("age_roles", {})
                role_id = age_roles.get(age_bracket)
                if role_id:
                    role = member.guild.get_role(role_id)
                    if role:
                        await member.add_roles(role)

        await channel.send(content=f"Here is {member.mention}'s intro!", embed=embed)

    # ==================== Commands ====================
    @app_commands.command(name="intro", description="Send your intro or someone else's")
    async def intro(self, interaction: discord.Interaction, member: discord.Member = None, row_num: int = None):
        member = member or interaction.user
        if not await self.check_command_permissions(interaction, "intro"):
            await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
            return
        await self.process_intro(member, row_num)
        await interaction.response.send_message(f"Intro processed for {member.mention}!", ephemeral=True)

    @app_commands.command(name="refresh_intros", description="Refresh the intro Excel file")
    async def refresh_intros(self, interaction: discord.Interaction):
        if not await self.check_command_permissions(interaction, "refresh_intros"):
            await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
            return
        self.workbook = None
        self.worksheet = None
        await self.init_excel()
        await interaction.response.send_message("Intro Excel file refreshed!", ephemeral=True)

async def setup(bot):
    await bot.add_cog(IntroSystem(bot))