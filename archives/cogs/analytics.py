import asyncio
import discord
from discord.ext import commands
from discord import app_commands
import json
import datetime
from utils.analytics_db import AnalyticsDB
from utils.config_manager import ConfigManager

class Analytics(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.db = AnalyticsDB()
        self.config_manager = ConfigManager('config.json')
        self.config = self.config_manager.load_config().get('analytics', {})

        # Initialize command configurations
        self.command_configs = {
            'activity': {
                'enabled': True,
                'required_roles': ['@everyone'],
                'permissions': []
            },
            'xpstats': {
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

        if 'permissions' in cmd_cfg:
            for perm in cmd_cfg['permissions']:
                if not getattr(interaction.user.guild_permissions, perm, False):
                    return False

        required_roles = cmd_cfg.get('required_roles', [])
        if required_roles and '@everyone' not in required_roles:
            user_roles = [str(role.id) for role in interaction.user.roles]
            if not any(role_id in user_roles for role_id in required_roles):
                return False

        return True

    async def process_message_for_analytics(self, message):
        try:
            if message.author.bot or not self.config.get('enabled', True):
                return

            guild_id = str(message.guild.id)
            user_id = str(message.author.id)

            # Load data or initialize fresh structure if file doesn't exist
            try:
                data = self.data_handler.load_data()
                if not isinstance(data, dict):  # In case file is corrupted
                    data = {}
            except (FileNotFoundError, json.JSONDecodeError):
                data = {}

            # Initialize guild data structure if not exists
            if guild_id not in data:
                data[guild_id] = {
                    'server_hours': {},
                    'users': {}
                }
            elif not isinstance(data[guild_id], dict):
                data[guild_id] = {
                    'server_hours': {},
                    'users': {}
                }

            # Initialize users structure if not exists
            if 'users' not in data[guild_id]:
                data[guild_id]['users'] = {}
            elif not isinstance(data[guild_id]['users'], dict):
                data[guild_id]['users'] = {}

            # Initialize user data structure if not exists
            if user_id not in data[guild_id]['users']:
                data[guild_id]['users'][user_id] = {
                    'message_count': 0,
                    'last_active': None,
                    'status_changes': [],
                    'xp_changes': [],
                    'online_time': 0,
                    'activity': {
                        'channels': {},
                        'active_hours': {}
                    },
                    'games': {}
                }
            elif not isinstance(data[guild_id]['users'][user_id], dict):
                data[guild_id]['users'][user_id] = {
                    'message_count': 0,
                    'last_active': None,
                    'status_changes': [],
                    'xp_changes': [],
                    'online_time': 0,
                    'activity': {
                        'channels': {},
                        'active_hours': {}
                    },
                    'games': {}
                }

            # Ensure activity structure exists
            if 'activity' not in data[guild_id]['users'][user_id]:
                data[guild_id]['users'][user_id]['activity'] = {
                    'channels': {},
                    'active_hours': {}
                }

            user_data = data[guild_id]['users'][user_id]
            user_data['message_count'] = user_data.get('message_count', 0) + 1
            user_data['last_active'] = datetime.datetime.now().isoformat()

            # Track channel activity
            channel_id = str(message.channel.id)
            if 'channels' not in user_data['activity']:
                user_data['activity']['channels'] = {}
            user_data['activity']['channels'][channel_id] = user_data['activity']['channels'].get(channel_id, 0) + 1

            # Track server-wide hour activity
            current_hour = str(datetime.datetime.now().hour)
            if 'server_hours' not in data[guild_id]:
                data[guild_id]['server_hours'] = {}
            data[guild_id]['server_hours'][current_hour] = data[guild_id]['server_hours'].get(current_hour, 0) + 1
    
            # Track user hour activity
            if 'active_hours' not in user_data['activity']:
                user_data['activity']['active_hours'] = {}
            user_data['activity']['active_hours'][current_hour] = user_data['activity']['active_hours'].get(current_hour, 0) + 1

            self.data_handler.save_data(data)
        except Exception as e:
            print(f"Error in on_message: {e}")
            raise  # Re-raise the exception after logging for debugging

    async def process_status_change(self, before, after):
        if not self.config.get('enabled', True) or before.guild is None:
            return

        try:
            guild_id = str(before.guild.id)
            user_id = str(before.id)

            # Load data with proper initialization if file doesn't exist
            try:
                data = self.data_handler.load_data()
                if not isinstance(data, dict):  # In case file is corrupted
                    data = {}
            except (FileNotFoundError, json.JSONDecodeError):
                data = {}

            # Initialize guild data structure if not exists
            if guild_id not in data:
                data[guild_id] = {
                    'server_hours': {},
                    'users': {}
                }

            # Initialize users structure if not exists
            if 'users' not in data[guild_id]:
                data[guild_id]['users'] = {}

            # Initialize user data structure if not exists
            if user_id not in data[guild_id]['users']:
                data[guild_id]['users'][user_id] = {
                    'message_count': 0,
                    'last_active': None,
                    'status_changes': [],
                    'xp_changes': [],
                    'online_time': 0,
                    'activity': {
                        'channels': {},
                        'active_hours': {}
                    },
                    'games': {}
                }

            user_data = data[guild_id]['users'][user_id]

            # Ensure all required fields exist
            if 'status_changes' not in user_data:
                user_data['status_changes'] = []
            if 'online_time' not in user_data:
                user_data['online_time'] = 0
            if 'games' not in user_data:
                user_data['games'] = {}

            # Track status changes
            if before.status != after.status:
                if not isinstance(user_data['status_changes'], list):
                    user_data['status_changes'] = []
                
                user_data['status_changes'].append({
                    'timestamp': datetime.datetime.now().isoformat(),
                    'from': str(before.status),
                    'to': str(after.status)
                })

                # Track last seen time when user goes offline
                if after.status == discord.Status.offline:
                    user_data['last_seen'] = datetime.datetime.now().isoformat()


                # Track online time
                if after.status != discord.Status.offline:
                    if 'last_online' not in user_data:
                        user_data['last_online'] = datetime.datetime.now().isoformat()
                    elif isinstance(user_data.get('last_online'), str):
                        try:
                            last_online = datetime.datetime.fromisoformat(user_data['last_online'])
                            time_online = (datetime.datetime.now() - last_online).total_seconds()
                            user_data['online_time'] = user_data.get('online_time', 0) + time_online
                            del user_data['last_online']
                        except ValueError:
                            # Handle invalid timestamp format
                            user_data['last_online'] = datetime.datetime.now().isoformat()

                # Track games played
                if after.activity and isinstance(after.activity, discord.Activity):
                    if after.activity.type in [discord.ActivityType.playing, 
                                             discord.ActivityType.listening,
                                             discord.ActivityType.watching,
                                             discord.ActivityType.streaming]:
                        game = after.activity.name
                        user_data['games'][game] = user_data['games'].get(game, 0) + 1

                self.data_handler.save_data(data)
        except Exception as e:
            print(f"Error in process_status_change: {e}")
            raise  # Re-raise for debugging

    @app_commands.command(name="activity", description="Show user activity analytics")
    async def activity(self, interaction: discord.Interaction, member: discord.Member = None):
        """Show detailed activity statistics for a user"""
        if not await self.check_command_permissions(interaction, 'activity'):
            return await interaction.response.send_message(
                "You don't have permission to use this command!",
                ephemeral=True
            )

        if member is None:
            member = interaction.user

        try:
            # Force-fetch the member to ensure up-to-date presence
            member = await interaction.guild.fetch_member(member.id)
        except discord.NotFound:
            await interaction.followup.send("Member not found.")
            return

        data = self.data_handler.load_data()
        guild_id = str(interaction.guild.id)
        user_id = str(member.id)

        # Check if data exists for this user
        if guild_id not in data or user_id not in data[guild_id].get('users', {}):
            return await interaction.response.send_message(
                f"No activity data available for {member.display_name}!",
                ephemeral=True
            )

        user_data = data[guild_id]['users'][user_id]
    
        embed = discord.Embed(
            title=f"{member.display_name}'s Activity Overview",
            color=discord.Color.blurple(),
            timestamp=datetime.datetime.now()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        
        status_changes = user_data.get("status_changes", [])

        if status_changes:
            latest_status = status_changes[-1].get("to", "")

            if latest_status == "online":
                embed.add_field(name="Last Active", value="This user is currently active (Online).", inline=True)

            elif latest_status == "dnd":
                last_online_time = None
                last_active_time = None

                for change in reversed(status_changes):
                    if change.get("to") == "online":
                        last_online_time = datetime.datetime.fromisoformat(change.get("timestamp"))
                        break

                if "last_active" in user_data:
                    last_active_time = datetime.datetime.fromisoformat(user_data["last_active"])

                recent_time = max(
                    [t for t in [last_online_time, last_active_time] if t is not None],
                    default=None
                )

                if recent_time:
                    embed.add_field(
                        name="Last Active",
                        value=f"User is in DND, this time may not be accurate.\nLast activity: <t:{int(recent_time.timestamp())}:R>",
                        inline=True
                    )
                else:
                    embed.add_field(name="Last Active", value="User is in DND, this time may not be accurate.\nNo recent activity recorded.", inline=True)

            else:
                last_seen = None
                last_active = None

                if "last_seen" in user_data:
                    last_seen = datetime.datetime.fromisoformat(user_data["last_seen"])

                if "last_active" in user_data:
                    last_active = datetime.datetime.fromisoformat(user_data["last_active"])

                recent_time = max(
                    [t for t in [last_seen, last_active] if t is not None],
                    default=None
                )

                if recent_time:
                    embed.add_field(
                        name="Last Active",
                        value=f"<t:{int(recent_time.timestamp())}:R>",
                        inline=True
                    )
                else:
                    embed.add_field(name="Last Active", value="No recent activity recorded.", inline=True)

        else:
            embed.add_field(name="Last Active", value="No status data available.", inline=True)

        
        # Online Time
        hours = user_data.get("online_time", 0) / 3600
        embed.add_field(name="Online Time", value=f"{hours:.1f} hours", inline=True)
        
        # Most Active Hour
        if "active_hours" in user_data.get("activity", {}):
            active_hours = user_data["activity"]["active_hours"]
            if active_hours:
                top_hour = max(active_hours.items(), key=lambda x: x[1])[0]
                embed.add_field(name="Most Active Hour", value=f"{int(top_hour)}:00", inline=True)
        
        # Most Played Games
        if "games" in user_data and user_data["games"]:
            top_games = sorted(user_data["games"].items(), key=lambda x: x[1], reverse=True)[:3]
            games_summary = "\n".join(f":video_game: {name}: {count} times" for name, count in top_games)
            embed.add_field(name="Top Games", value=games_summary, inline=False)
        
        # Server-wide stats
        if "server_hours" in data[guild_id] and data[guild_id]["server_hours"]:
            busiest_hour = max(data[guild_id]["server_hours"].items(), key=lambda x: x[1])[0]
            embed.add_field(name="Busiest Server Hour", value=f"{int(busiest_hour)}:00", inline=True)
        
        await interaction.response.send_message(embed=embed, ephemeral=True)

async def setup(bot):
    await bot.add_cog(Analytics(bot))
