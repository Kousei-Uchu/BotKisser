import discord
from discord.ext import commands
from discord import app_commands
import json
import os
from dotenv import load_dotenv
import sys
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))
from utils.config_manager import ConfigManager

load_dotenv()

GUILD_ID = 1071601574616498248

intents = discord.Intents.all()
bot = commands.Bot(
    allowed_contexts=discord.app_commands.AppCommandContext(guild=True),
    command_prefix=os.getenv("COMMAND_PREFIX", "!"), # Omitted prefix due to required argument but I don't want members knowing the prefix used to bypass the permission checks I was too lazy to set up properly
    intents=intents,
    help_command=None,
    activity=discord.Activity(type=discord.ActivityType.watching, name="You")
)

config_manager = ConfigManager('config.json')
config = config_manager.load_config()


@bot.event
async def on_ready():
    print(f'Logged in as {bot.user.name} ({bot.user.id})')


async def load_cogs():
    for filename in os.listdir('./cogs'):
        if filename.endswith('.py'):
            try:
                await bot.load_extension(f'cogs.{filename[:-3]}')
                print(f'Loaded cog: {filename}')
            except Exception as e:
                print(f'Failed to load cog {filename}: {e}')


# setup_hook runs once before the bot connects — safe for cog loading and tree sync
async def setup_hook():
    await load_cogs()
    await bot.tree.sync()

bot.setup_hook = setup_hook


@bot.command()
@commands.has_permissions(administrator=True)
async def reload(ctx, cog_name: str):
    try:
        await bot.reload_extension(f'cogs.{cog_name}')
        await ctx.send(f'Reloaded {cog_name} successfully!')
    except Exception as e:
        await ctx.send(f'Failed to reload {cog_name}: {e}')


bot.run(os.getenv("DISCORD_TOKEN"))