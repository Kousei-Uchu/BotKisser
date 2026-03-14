import discord
from discord.ext import commands
from discord import app_commands
import random
import requests
from utils.config_manager import ConfigManager
from utils.data_handler import DataHandler
import datetime

class Fun(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = ConfigManager('config.json').load_config().get('fun', {})
        self.afk_users = {}  # user_id -> {status, time, ignored_channels}
        self.fire_data_handler = DataHandler('data/fireboard.json')
        self.fire_data = self.fire_data_handler.load_data()
        self.fire_data.setdefault('posts', {})

        self.command_configs = {
            'roll':        {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'flip':        {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'rps':         {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'dadjoke':     {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'cat':         {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'dog':         {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
        }

        for name, cfg in self.config.get('commands', {}).items():
            if name in self.command_configs:
                self.command_configs[name].update(cfg)

    async def check_command_permissions(self, interaction: discord.Interaction, command_name: str):
        cfg = self.command_configs.get(command_name, {})
        if not cfg.get('enabled', True):
            return False
        for perm in cfg.get('permissions', []):
            if not getattr(interaction.user.guild_permissions, perm, False):
                return False
        req = cfg.get('required_roles', [])
        if req and '@everyone' not in req:
            user_roles = [str(role.id) for role in interaction.user.roles]
            if not any(role in user_roles for role in req):
                return False
        return True
    
    @app_commands.command(name="heart", description="Unit Heart")
    async def heart(self, interaction: discord.Interaction, memorycode: str):
        if memorycode == "MUSICAL MEMORIES":
            await interaction.response.send_message("disPxPyevwc")
        else:
            await interaction.response.send_message("X")

    @app_commands.command(name="roll", description="Roll a dice. Format: NdM (e.g., 2d6)")
    async def roll(self, interaction: discord.Interaction, dice: str = "d20"):
        if not await self.check_command_permissions(interaction, 'roll'):
            return await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)
        try:
            if 'd' not in dice.lower():
                raise ValueError("Missing 'd' in dice format.")
            parts = dice.lower().split('d')
            qty = int(parts[0]) if parts[0] else 1
            sides = int(parts[1])
            if qty > 100 or sides > 1000:
                return await interaction.response.send_message("Max roll is 100d1000!", ephemeral=True)
            rolls = [random.randint(1, sides) for _ in range(qty)]
            total = sum(rolls)
            if qty == 1:
                await interaction.response.send_message(f"You rolled a {rolls[0]}!")
            else:
                await interaction.response.send_message(f"Rolls: {', '.join(map(str, rolls))} (Total: {total})")
        except Exception:
            await interaction.response.send_message("Invalid format! Use NdM, e.g. 2d6.", ephemeral=True)

    @app_commands.command(name="flip", description="Flip a coin.")
    async def flip(self, interaction: discord.Interaction):
        if not await self.check_command_permissions(interaction, 'flip'):
            return await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)
        await interaction.response.send_message(f"🪙 {random.choice(['Heads', 'Tails'])}!")

    @app_commands.command(name="rps", description="Play Rock, Paper, Scissors.")
    @app_commands.describe(choice="Choose rock, paper, or scissors")
    async def rps(self, interaction: discord.Interaction, choice: str):
        if not await self.check_command_permissions(interaction, 'rps'):
            return await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)
        choice = choice.lower()
        if choice not in ["rock", "paper", "scissors"]:
            return await interaction.response.send_message("Choose rock, paper, or scissors!", ephemeral=True)
        bot_choice = random.choice(["rock", "paper", "scissors"])
        if choice == bot_choice:
            res = "It's a tie!"
        elif (choice == "rock" and bot_choice == "scissors") or \
             (choice == "paper" and bot_choice == "rock") or \
             (choice == "scissors" and bot_choice == "paper"):
            res = "You win!"
        else:
            res = "I win!"
        await interaction.response.send_message(f"You: {choice.title()}\nMe: {bot_choice.title()}\n**{res}**")

    @app_commands.command(name="dadjoke", description="Tell a dad joke.")
    async def dadjoke(self, interaction: discord.Interaction):
        if not await self.check_command_permissions(interaction, 'dadjoke'):
            return await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)
        try:
            r = requests.get("https://icanhazdadjoke.com/", headers={"Accept": "application/json"})
            r.raise_for_status()
            joke = r.json().get("joke", "No joke!")
            await interaction.response.send_message(joke)
        except Exception:
            await interaction.response.send_message("Could not fetch a joke.", ephemeral=True)

    @app_commands.command(name="cat", description="Get a random cat picture.")
    async def cat(self, interaction: discord.Interaction):
        if not await self.check_command_permissions(interaction, 'cat'):
            return await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)
        try:
            r = requests.get("https://api.thecatapi.com/v1/images/search")
            r.raise_for_status()
            url = r.json()[0]['url']
            await interaction.response.send_message(url)
        except Exception:
            await interaction.response.send_message("Could not fetch cat pic.", ephemeral=True)

    @app_commands.command(name="dog", description="Get a random dog picture.")
    async def dog(self, interaction: discord.Interaction):
        if not await self.check_command_permissions(interaction, 'dog'):
            return await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)
        try:
            r = requests.get("https://dog.ceo/api/breeds/image/random")
            r.raise_for_status()
            url = r.json().get('message')
            await interaction.response.send_message(url)
        except Exception:
            await interaction.response.send_message("Could not fetch dog pic.", ephemeral=True)

    # @app_commands.command(name="status", description="Change the bot's status.")
    # async def status(self, interaction: discord.Interaction):
    #     if not await self.check_command_permissions(interaction, 'status'):
    #         return await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)

    #     try:
    #         await self.bot.change_presence(status="Watching over The Den")
    #         await interaction.response.send_message("Changed!", ephemeral=True)
    #     except Exception:
    #         await interaction.response.send_message("Error changing status.", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Fun(bot))
