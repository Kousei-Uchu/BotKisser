import discord
from discord import app_commands
from discord.ext import commands
from utils.config_manager import ConfigManager
from utils.sqlite_handler import SQLiteHandler

class Maintainance(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # Moderation DB setup
        self.bot_sql = SQLHandler("data/bot.db")
        self.mod_db = ModerationDB(self.bot_sql)

        # Analytics DB setup
        self.analytics_db = AnalyticsDB()

    @app_commands.command(name="cleanup_db", description="Clean up old entries from the database")
    async def cleanup_db(self, interaction: discord.Interaction):
        if not await self.check_command_permissions(interaction, "cleanup_db"):
            return await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)

        warn_deleted = self.mod_db.cleanup_warnings_duplicates()
        await interaction.channel.send_message(f"🧹 Deleted {warn_deleted} duplicate warning entries.")

        modlog_deleted = self.mod_db.cleanup_modlogs_duplicates()
        await interaction.channel.send_message(f"🧹 Deleted {modlog_deleted} duplicate moderation log entries.")

        status_deleted = self.analytics_db.cleanup_old_entries()
        await interaction.channel.send_message(f"🧹 Deleted {status_deleted} old status change entries.")
        

        await interaction.response.send_message(f"🧹 Database cleanup complete. Deleted {deleted_entries} old entries.")





async def setup(bot):
    await bot.add_cog(Maintainance(bot))