import discord
from discord import app_commands
from discord.ext import commands
from datetime import datetime
import tempfile
import openpyxl
import requests
import os

from utils.config_manager import ConfigManager

class IntroSystem(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config_manager = ConfigManager('config.json')
        self.config = self.config_manager.load_config().get('intro', {})
        self.workbook = None
        self.worksheet = None
        self.temp_file = None

        self.command_configs = {
            'intro': {
                'enabled': True,
                'required_roles': ['@everyone'],
                'permissions': []
            },
            'refresh_intros': {
                'enabled': True,
                'required_roles': ['@everyone'],
                'permissions': []
            }
        }
        self.update_configs()

    def update_configs(self):
        if 'commands' in self.config:
            for cmd, cfg in self.config['commands'].items():
                if cmd in self.command_configs:
                    self.command_configs[cmd].update(cfg)

    async def check_command_permissions(self, interaction: discord.Interaction, command_name):
        if command_name not in self.command_configs:
            return False

        cmd_cfg = self.command_configs[command_name]
        if not cmd_cfg.get('enabled', True):
            return False

        for perm in cmd_cfg.get('permissions', []):
            if not getattr(interaction.user.guild_permissions, perm, False):
                return False

        required_roles = cmd_cfg.get('required_roles', [])
        if required_roles and '@everyone' not in required_roles:
            user_roles = [str(role.id) for role in interaction.user.roles]
            if not any(role_id in user_roles for role_id in required_roles):
                return False

        return True

    def init_excel(self):
        try:
            excel_file_path = self.config.get('excel_file_path')
            if not os.path.exists(excel_file_path):
                print(f"[init_excel] Excel file not found.")
                return

            self.workbook = openpyxl.load_workbook(excel_file_path)
            self.worksheet = self.workbook.active
        except Exception as e:
            print(f"[init_excel] Failed to load Excel file: {e}")

    def get_all_records(self):
        try:
            rows = list(self.worksheet.iter_rows(values_only=True))
            if not rows:
                print("[get_all_records] No rows found.")
                return []
            headers = rows[0]
            data = [dict(zip(headers, row)) for row in rows[1:]]
            return data
        except Exception as e:
            print(f"[get_all_records] Error: {e}")
            return []

    def calculate_age(self, birth_year_or_age):
        current_year = datetime.now().year
        try:
            possible_age = int(birth_year_or_age)

            # Prioritize detecting birth years first
            if 1900 <= possible_age <= current_year:
                age = current_year - possible_age
                return age

            # Then fallback to interpreting as age
            if 8 <= possible_age <= 100:
                return possible_age

        except Exception as e:
            print(f"[calculate_age] Failed to parse age input: {e}")
    
        print(f"[calculate_age] Could not determine age.")
        return None


    def get_age_bracket(self, age):
        if age < 16:
            return "13-15"
        elif age < 18:
            return "16-17"
        elif age < 21:
            return "18-20"
        elif age < 31:
            return "21-30"
        elif age < 41:
            return "31-40"
        return "40+"

    async def on_member_approve(self, user):
        if not self.config.get('enabled', True):
            return
        self.init_excel()
        if not self.worksheet:
            print("[on_member_join] Worksheet not loaded.")
            return
        await self.process_intro(user)
        message_content = f"**Welcome to The Den {user.mention}! We're so glad to have you!** Make sure to grab *the rest* of your roles in <id:customize>! *(There are more than in the onboarding)*\n\n<@&1296350497929695232> come say hi! Some more info about them is in <#1071601575744766038>!"
        channel_id = 1071601576252289158
        channel = self.bot.get_channel(channel_id)
        await channel.send(content=message_content)

    async def process_intro(self, member: discord.Member, row_num: int = None):
        try:
            records = self.get_all_records()
            user_record = None

            if row_num is not None and 1 <= row_num <= len(records):
                user_record = records[row_num - 1]
            else:
                # Iterate in reverse so the last match is used
                for record in reversed(records):
                    username_match = str(record.get('Username', '')).lower() == str(member).lower()
                    preferred_name_match = str(record.get("What's your preferred name?", '')).lower() == str(member.name).lower()

                    if username_match or preferred_name_match:
                        user_record = record
                        break

            if not user_record:
                print("[process_intro] No matching record found.")
                return

            channel_id = self.config.get('channel_id')
            if not channel_id:
                print("[process_intro] No channel ID configured.")
                return

            channel = self.bot.get_channel(channel_id)
            if not channel:
                print(f"[process_intro] Channel not found: {channel_id}")
                return

            message_content = f"Here is {member.mention}'s intro!"
    
            embed = discord.Embed(
                title=f"Get to know me!",
                color=discord.Color.blue()
            )

            # Updated to match QNACog's exact question texts
            fields = {
                "My Preferred Name": "Preferred Name",
                "My Pronouns": "Pronouns",
                "My Reddit Username": "Reddit Username",
                "My Pronouns Page": "Pronouns Page",
                "More about me": "About",
                "My Fursona's Name": "Fursona Name",
                "My Fursona's Species": "Fursona Species",
                "My Fursona's info": "About Fursona",
                "My Favourite Quote": "Favourite Quote"
            }

            for embed_field, sheet_field in fields.items():
                value = user_record.get(sheet_field, 'N/A')
                if value and str(value).lower() not in ['', 'n/a', 'Skipped']:
                    embed.add_field(name=embed_field, value=value, inline=False)

            # Age processing (uses the exact question text from QNACog)
            age_input = user_record.get("Age", "")
            if age_input:
                age = self.calculate_age(age_input)
                if age is not None:
                    age_bracket = self.get_age_bracket(age)
                    bracket_roles = self.config.get('age_roles', {})
                    role_id = bracket_roles.get(age_bracket)
                    if role_id:
                        role = member.guild.get_role(role_id)
                        if role:
                            await member.add_roles(role)

            await channel.send(content=message_content, embed=embed)

        except Exception as e:
            print(f"[process_intro] Error: {e}")

    @app_commands.command(name="intro", description="Manually send your intro or someone else's")
    async def intro(self, interaction: discord.Interaction, member: discord.Member = None, row_num: int = None):
        member = member or interaction.user

        if not await self.check_command_permissions(interaction, 'intro'):
            await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
            return

        self.init_excel()
        await self.process_intro(member, row_num)
        await interaction.response.send_message(f"Intro processed for {member.mention}!")

    @app_commands.command(name="refresh_intros", description="Refresh the intro Excel file from the cloud")
    async def refresh_intros(self, interaction: discord.Interaction):
        if not await self.check_command_permissions(interaction, 'refresh_intros'):
            await interaction.response.send_message("You don't have permission to use this command!", ephemeral=True)
            return

        self.init_excel()
        await interaction.response.send_message("Intro Excel file refreshed!")

async def setup(bot):
    await bot.add_cog(IntroSystem(bot))
