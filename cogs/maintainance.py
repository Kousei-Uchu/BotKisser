import discord
from discord import app_commands
from discord.ext import commands

from utils.config_manager import ConfigManager
from utils.sqlite_handler import SQLiteHandler
from utils.moderation_db import ModerationDB
from utils.analytics_db import AnalyticsDB


class Maintenance(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        self.bot_sql = SQLiteHandler("data/bot.db")
        self.mod_db = ModerationDB(self.bot_sql)

        self.analytics_db = AnalyticsDB()

    @app_commands.command(
        name="cleanup_db",
        description="Clean up old entries from the database"
    )
    async def cleanup_db(self, interaction: discord.Interaction):

        if not await self.check_command_permissions(interaction, "cleanup_db"):
            return await interaction.response.send_message(
                "❌ You don't have permission!",
                ephemeral=True
            )

        await interaction.response.defer(ephemeral=True)

        warn_deleted = self.mod_db.cleanup_warnings_duplicates()
        modlog_deleted = self.mod_db.cleanup_modlogs_duplicates()
        status_deleted = self.analytics_db.cleanup_old_entries()

        total_deleted = (
            warn_deleted +
            modlog_deleted +
            status_deleted
        )

        await interaction.followup.send(
            f"🧹 Database cleanup complete.\n"
            f"- Warning duplicates removed: {warn_deleted}\n"
            f"- Modlog duplicates removed: {modlog_deleted}\n"
            f"- Old analytics entries removed: {status_deleted}\n"
            f"- Total deleted: {total_deleted}"
        )


async def setup(bot):
    await bot.add_cog(Maintenance(bot))