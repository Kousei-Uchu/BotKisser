import discord
from discord.ext import commands
from discord import app_commands
import datetime

from utils.db_handlers.analytics_db import AnalyticsDB
from utils.config_manager import ConfigManager


class Analytics(commands.Cog):

    def __init__(self, bot):

        self.bot = bot

        self.db = AnalyticsDB()

        self.config_manager = ConfigManager("config.json")
        self.config = self.config_manager.load_config().get("analytics", {})

        self.command_configs = {
            "activity": {
                "enabled": True,
                "required_roles": ["@everyone"],
                "permissions": []
            },
            "leaderboard": {
                "enabled": True,
                "required_roles": ["@everyone"],
                "permissions": []
            }
        }

        self.update_configs()

    def update_configs(self):

        if "commands" in self.config:

            for cmd, cfg in self.config["commands"].items():

                if cmd in self.command_configs:

                    self.command_configs[cmd].update(cfg)

    async def check_command_permissions(self, interaction, command_name):

        if command_name not in self.command_configs:
            return False

        cfg = self.command_configs[command_name]

        if not cfg.get("enabled", True):
            return False

        required_roles = cfg.get("required_roles", [])

        if required_roles and "@everyone" not in required_roles:

            user_roles = [str(role.id) for role in interaction.user.roles]

            if not any(r in user_roles for r in required_roles):
                return False

        return True

    # ---------------------
    # MESSAGE TRACKING
    # ---------------------

    async def process_message_for_analytics(self, message):

        if message.author.bot:
            return

        if not self.config.get("enabled", True):
            return

        await self.db.log_message(
            str(message.guild.id),
            str(message.author.id),
            str(message.channel.id)
        )

    # ---------------------
    # STATUS TRACKING
    # ---------------------

    async def process_status_change(self, before, after):

        if before.guild is None:
            return

        if before.status == after.status:
            return

        await self.db.log_status_change(
            str(before.guild.id),
            str(before.id),
            str(before.status),
            str(after.status)
        )

        if after.activity:

            if isinstance(after.activity, discord.Activity):

                if after.activity.name:

                    await self.db.log_game(
                        str(after.guild.id),
                        str(after.id),
                        after.activity.name
                    )

    # ---------------------
    # ACTIVITY COMMAND
    # ---------------------

    @app_commands.command(name="activity", description="User analytics")

    async def activity(self, interaction: discord.Interaction, member: discord.Member = None):

        if member is None:
            member = interaction.user

        row = self.db.get_user(str(interaction.guild.id), str(member.id))

        if not row:

            await interaction.response.send_message(
                "No activity recorded.",
                ephemeral=True
            )

            return

        embed = discord.Embed(
            title=f"{member.display_name} Activity",
            color=discord.Color.blurple(),
            timestamp=datetime.datetime.utcnow()
        )

        embed.add_field(
            name="Messages",
            value=row["message_count"],
            inline=True
        )

        if row["last_active"]:

            t = datetime.datetime.fromisoformat(row["last_active"])

            embed.add_field(
                name="Last Active",
                value=f"<t:{int(t.timestamp())}:R>",
                inline=True
            )

        games = self.db.get_user_games(
            str(interaction.guild.id),
            str(member.id)
        )

        if games:

            text = "\n".join(
                f"🎮 {g['game']} — {g['count']}"
                for g in games
            )

            embed.add_field(
                name="Top Games",
                value=text,
                inline=False
            )

        busiest = self.db.get_busiest_hour(str(interaction.guild.id))

        if busiest:

            embed.add_field(
                name="Busiest Server Hour",
                value=f"{busiest['hour']}:00",
                inline=True
            )

        await interaction.response.send_message(embed=embed)

    # ---------------------
    # LEADERBOARD
    # ---------------------

    @app_commands.command(name="messages_leaderboard", description="Most active users")

    async def messages_leaderboard(self, interaction: discord.Interaction):

        rows = self.db.get_top_users(str(interaction.guild.id), 10)

        if not rows:

            await interaction.response.send_message(
                "No data yet."
            )

            return

        text = ""

        for i, row in enumerate(rows, 1):

            user = interaction.guild.get_member(int(row["user_id"]))

            name = user.display_name if user else row["user_id"]

            text += f"**{i}. {name}** — {row['message_count']} messages\n"

        embed = discord.Embed(
            title="Server Activity Leaderboard",
            description=text,
            color=discord.Color.blurple()
        )

        await interaction.response.send_message(embed=embed)


async def setup(bot):

    await bot.add_cog(Analytics(bot))