"""
moderation.py
-------------
Discord moderation cog.  All persistence is handled via ModerationDB (SQLite).
"""

import asyncio
import datetime

import discord
from discord import app_commands
from discord.ext import commands, tasks

from utils.sql_handler import SQLHandler
from utils.db_handlers.moderation_db import ModerationDB
from utils.config_manager import ConfigManager


# --------------------------------------------------------------------------- #
#  Utility                                                                      #
# --------------------------------------------------------------------------- #

def parse_time(time_str: str) -> int:
    """Parse a time string like 1d, 2h, 30m into seconds."""
    if not time_str:
        return 0

    units = {
        's': 1,
        'm': 60,
        'h': 60 * 60,
        'd': 24 * 60 * 60,
        'w': 7 * 24 * 60 * 60,
    }

    try:
        num = int(time_str[:-1])
        unit = time_str[-1].lower()
        if unit not in units:
            raise ValueError
        return num * units[unit]
    except (ValueError, IndexError):
        raise ValueError(f"Invalid time format: {time_str}. Use format like 1h, 30m, 2d")


# --------------------------------------------------------------------------- #
#  Cog                                                                          #
# --------------------------------------------------------------------------- #

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot

        # ── persistence ──────────────────────────────────────────────────── #
        self.sql = SQLHandler("data/bot.db")
        self.db  = ModerationDB(self.sql)

        # ── config ───────────────────────────────────────────────────────── #
        self.config_manager = ConfigManager('config.json')
        self.config = self.config_manager.load_config().get('moderation', {})

        # ── command permission matrix ─────────────────────────────────────── #
        self.command_configs = {
            'deafen':      {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['deafen_members']},
            'undeafen':    {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['deafen_members']},
            'kick':        {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['kick_members']},
            'ban':         {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['ban_members']},
            'unban':       {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['ban_members']},
            'softban':     {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['ban_members']},
            'mute':        {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_roles']},
            'unmute':      {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_roles']},
            'members':     {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'rolepersist': {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_roles']},
            'temprole':    {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_roles']},
            'warn':        {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['kick_members']},
            'warnings':    {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'delwarn':     {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['kick_members']},
            'note':        {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['kick_members']},
            'notes':       {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'editnote':    {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['kick_members']},
            'delnote':     {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['kick_members']},
            'clearnotes':  {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['kick_members']},
            'modlogs':     {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'case':        {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'moderations': {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'lock':        {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_channels']},
            'unlock':      {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_channels']},
            'lockdown':    {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_channels']},
            'ignored':     {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'reason':      {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['kick_members']},
            'modstats':    {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'duration':    {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['kick_members']},
            'clean':       {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_messages']},
            'fireboard':   {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
        }
        self._update_configs()

        # ── background task ───────────────────────────────────────────────── #
        self._timed_loop.start()

    # ---------------------------------------------------------------------- #
    #  Config helpers                                                          #
    # ---------------------------------------------------------------------- #

    def _update_configs(self):
        if 'commands' in self.config:
            for cmd, cfg in self.config['commands'].items():
                if cmd in self.command_configs:
                    self.command_configs[cmd].update(cfg)

    async def check_command_permissions(self, interaction: discord.Interaction, command_name: str) -> bool:
        cfg = self.command_configs.get(command_name, {})
        if not cfg.get('enabled', True):
            return False
        req = cfg.get('required_roles', [])
        if req and '@everyone' not in req:
            user_roles = [str(r.id) for r in interaction.user.roles]
            if not any(rid in user_roles for rid in req):
                return False
        for p in cfg.get('permissions', []):
            if not getattr(interaction.user.guild_permissions, p, False):
                return False
        return True

    async def can_moderate_member(self, interaction: discord.Interaction, member: discord.Member) -> bool:
        """Role-hierarchy check; allows self-moderation and ignores the muted role."""
        muted_role_id = self.config.get('mute_role')
        muted_role = interaction.guild.get_role(muted_role_id) if muted_role_id else None

        def top_role_excluding_muted(m):
            roles = [r for r in m.roles if r != muted_role]
            if not roles:
                return m.top_role  # fallback — handles @everyone-only members safely
            return sorted(roles, key=lambda r: r.position, reverse=True)[0]

        if interaction.user == member:
            return True

        user_top   = top_role_excluding_muted(interaction.user)
        member_top = top_role_excluding_muted(member)

        return user_top > member_top

    # ---------------------------------------------------------------------- #
    #  Background loop – timed actions                                        #
    # ---------------------------------------------------------------------- #

    @tasks.loop(seconds=30)
    async def _timed_loop(self):
        now = datetime.datetime.utcnow().timestamp()
        expired = self.db.get_expired_actions(now)

        for action in expired:
            guild = self.bot.get_guild(action["guild_id"])
            if not guild:
                self.db.delete_timed_action(action["id"])
                continue

            user_id      = action["user_id"]
            action_type  = action["type"]

            try:
                if action_type == 'ban' and user_id:
                    await guild.unban(discord.Object(id=user_id))

                elif action_type == 'mute' and user_id:
                    member = guild.get_member(user_id)
                    role   = guild.get_role(int(self.config['mute_role']))
                    if member and role:
                        await member.remove_roles(role)
                        try:
                            await member.send(
                                self.config['unmute_message'].format(reason='Time expired')
                            )
                        except discord.Forbidden:
                            pass

                elif action_type == 'temprole' and user_id:
                    member = guild.get_member(user_id)
                    role   = guild.get_role(action["role_id"])
                    if member and role:
                        await member.remove_roles(role)

                elif action_type == 'unlock_ch':
                    channel = guild.get_channel(action["channel_id"])
                    if channel:
                        await channel.set_permissions(
                            guild.default_role, send_messages=True
                        )
                        self.db.unlock_channel(str(guild.id), action["channel_id"])

            except Exception as e:
                print(f"[timed_loop] Error handling action id={action['id']}: {e}")

            self.db.delete_timed_action(action["id"])

    # ---------------------------------------------------------------------- #
    #  Member join – restore persisted roles                                  #
    # ---------------------------------------------------------------------- #

    @commands.Cog.listener()
    async def on_member_join(self, member: discord.Member):
        gid = str(member.guild.id)
        uid = str(member.id)
        for role_id in self.db.get_persisted_roles(gid, uid):
            role = member.guild.get_role(role_id)
            if role:
                await member.add_roles(role)

    # ---------------------------------------------------------------------- #
    #  Logging helper                                                          #
    # ---------------------------------------------------------------------- #

    async def log(self, interaction: discord.Interaction, action: str, target,
                  reason: str = None, duration: str = None) -> int:
        gid = str(interaction.guild.id)

        if isinstance(target, (discord.Member, discord.User)):
            user_id = target.id
        elif isinstance(target, discord.Object):
            user_id = target.id
        else:
            try:
                user_id = int(target)
            except (ValueError, TypeError):
                user_id = None

        case_id = self.db.add_modlog(
            guild_id=gid,
            action=action,
            user_id=user_id,
            moderator_id=interaction.user.id,
            reason=reason,
            duration=duration,
        )

        embed = discord.Embed(
            title=f"Moderation Log: Case #{case_id}",
            description=f"Action: {action}",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow(),
        )
        embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
        embed.add_field(name="Target",    value=f"<@{user_id}>" if user_id else "Server-wide", inline=False)
        embed.add_field(name="Reason",    value=reason or "No reason provided", inline=False)
        embed.add_field(name="Duration",  value=duration or "N/A", inline=False)
        embed.add_field(name="Timestamp", value=datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), inline=False)

        log_channel_id = self.config.get("mod_log_channel_id")
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(embed=embed)
            else:
                print(f"[log] Log channel {log_channel_id} not found.")
        else:
            print("[log] mod_log_channel_id not set in config.")

        return case_id

    # ====================================================================== #
    #  COMMANDS                                                                #
    # ====================================================================== #

    @app_commands.command(name="clean", description="Clean up the bot's responses")
    @app_commands.describe(amount="Number of messages to clean (default 10)")
    async def clean(self, interaction: discord.Interaction, amount: int = 10):
        if not await self.check_command_permissions(interaction, 'clean'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        await interaction.response.defer(ephemeral=True)

        def is_bot(m):
            return m.author == self.bot.user

        # Pass amount directly so we don't purge more than requested
        deleted = await interaction.channel.purge(limit=amount, check=is_bot)

        msg = await interaction.followup.send(
            self.config.get('clean_message', f"Deleted {len(deleted)} messages."),
            ephemeral=True,
        )
        await asyncio.sleep(5)
        await msg.delete()

    @app_commands.command(name="deafen", description="Deafen a member in voice channel")
    @app_commands.describe(member="Member to deafen")
    async def deafen(self, interaction: discord.Interaction, member: discord.Member):
        if not await self.check_command_permissions(interaction, 'deafen'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        await member.edit(deafen=True)
        await interaction.response.send_message(f"🔇 Deafened {member.mention}")

    @app_commands.command(name="undeafen", description="Undeafen a member in voice channel")
    @app_commands.describe(member="Member to undeafen")
    async def undeafen(self, interaction: discord.Interaction, member: discord.Member):
        if not await self.check_command_permissions(interaction, 'undeafen'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        if not await self.can_moderate_member(interaction, member):
            return await interaction.response.send_message("You cannot moderate this member as they are higher ranked.")
        await member.edit(deafen=False)
        await interaction.response.send_message(f"🔊 Undeafened {member.mention}")

    @app_commands.command(name="crisis", description="Put a member in the Crisis Channel")
    @app_commands.describe(member="Member in crisis")
    async def crisis(self, interaction: discord.Interaction, member: discord.Member):
        role = interaction.guild.get_role(1329393692657582141)
        await member.add_roles(role)
        await interaction.response.send_message(f"{member.mention} has been locked to crisis channel")

    @app_commands.command(name="crisis_end", description="Allow a member to move from Crisis Channel")
    @app_commands.describe(member="Member to remove from crisis")
    async def crisis_end(self, interaction: discord.Interaction, member: discord.Member):
        role = interaction.guild.get_role(1329393692657582141)
        await member.remove_roles(role)
        await interaction.response.send_message(f"{member.mention} has been unlocked from crisis channel")

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(member="Member to kick", reason="Reason for kick")
    async def kick(self, interaction: discord.Interaction,
                   member: discord.Member,
                   reason: str = "No reason provided"):
        if not await self.check_command_permissions(interaction, 'kick'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        if not await self.can_moderate_member(interaction, member):
            return await interaction.response.send_message("You cannot moderate this member as they are higher ranked.")

        try:
            await member.send(self.config['kick_message'].format(reason=reason))
        except (discord.Forbidden, KeyError):
            pass

        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 Kicked {member.mention}")
        await self.log(interaction, "Kick", member, reason)

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(member="Member to ban", duration="Duration (e.g. 1d, 2h)", reason="Reason for ban")
    async def ban(self, interaction: discord.Interaction,
                  member: discord.Member,
                  duration: str = None,
                  reason: str = "No reason provided"):
        if not await self.check_command_permissions(interaction, 'ban'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        if not await self.can_moderate_member(interaction, member):
            return await interaction.response.send_message("You cannot moderate this member as they are higher ranked.")

        # Validate duration BEFORE executing the ban so we don't ban without a timer
        end_ts = None
        if duration:
            try:
                end_ts = datetime.datetime.utcnow().timestamp() + parse_time(duration)
            except ValueError:
                return await interaction.response.send_message(
                    "❌ Invalid duration format. Use like 1h, 30m, 2d", ephemeral=True
                )

        try:
            await member.send(
                self.config['ban_message'].format(duration=duration or "permanently", reason=reason)
            )
        except (discord.Forbidden, KeyError):
            pass

        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 Banned {member.mention}")
        await self.log(interaction, "Ban", member, reason, duration)

        if end_ts:
            self.db.add_timed_action(
                guild_id=interaction.guild.id,
                action_type='ban',
                end_ts=end_ts,
                user_id=member.id,
            )

    @app_commands.command(name="unban", description="Unban a user from the server")
    @app_commands.describe(user_id="ID of user to unban", reason="Reason for unban")
    async def unban(self, interaction: discord.Interaction,
                    user_id: str,
                    reason: str = "No reason provided"):
        if not await self.check_command_permissions(interaction, 'unban'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        try:
            uid = int(user_id)
        except ValueError:
            return await interaction.response.send_message("❌ Invalid user ID format.", ephemeral=True)

        user = discord.Object(id=uid)
        try:
            await interaction.guild.unban(user, reason=reason)
            await interaction.response.send_message(f"🔓 Unbanned user {uid}")
            await self.log(interaction, "Unban", user, reason)
        except discord.NotFound:
            await interaction.response.send_message("❌ User is not banned.", ephemeral=True)

    @app_commands.command(name="softban", description="Softban a member (kick with message deletion)")
    @app_commands.describe(member="Member to softban", reason="Reason for softban")
    async def softban(self, interaction: discord.Interaction,
                      member: discord.Member,
                      reason: str = "No reason provided"):
        if not await self.check_command_permissions(interaction, 'softban'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        if not await self.can_moderate_member(interaction, member):
            return await interaction.response.send_message("You cannot moderate this member as they are higher ranked.")

        await member.ban(reason=reason, delete_message_days=7)
        await interaction.guild.unban(member)
        await interaction.response.send_message(f"🛑 Softbanned {member.mention}")
        await self.log(interaction, "Softban", member, reason)

    @app_commands.command(name="members", description="List members in specified roles")
    @app_commands.describe(roles="Roles to check (mention or ID)")
    async def members(self, interaction: discord.Interaction, roles: str):
        if not await self.check_command_permissions(interaction, 'members'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        role_objects = []
        for part in roles.split():
            try:
                role_id = int(part.strip('<@&>'))
                role = interaction.guild.get_role(role_id)
                if role:
                    role_objects.append(role)
            except ValueError:
                continue

        if not role_objects:
            return await interaction.response.send_message(
                "❌ No valid roles provided.", ephemeral=True
            )

        unique_members = set()
        for role in role_objects[:5]:
            unique_members.update(role.members)

        member_count = len(unique_members)
        mentions     = [m.mention for m in list(unique_members)[:90]]
        role_names   = ", ".join(f"'{r.name}'" for r in role_objects[:5])
        if len(role_objects) > 5:
            role_names += f" (and {len(role_objects)-5} more)"

        parts = [
            f"**Found {member_count} members in specified roles:**",
            "",
            ", ".join(mentions) if mentions else "No members found.",
            f"\n*Roles checked: {role_names}*",
        ]
        await interaction.response.send_message("\n".join(parts), ephemeral=True)

    @app_commands.command(name="announce", description="Send an announcement with markdown formatting.")
    async def announce(self, interaction: discord.Interaction,
                       content: str,
                       channel: discord.TextChannel = None):
        content = content.replace("\\n", "\n")
        channel = channel or interaction.channel
        await channel.send(content)
        await interaction.response.send_message(f"Announcement sent in {channel.mention}!", ephemeral=True)

    @app_commands.command(name="temprole", description="Assign a temporary role")
    @app_commands.describe(member="Member", role="Role to assign", duration="Duration (e.g. 1h, 2d)")
    async def temprole(self, interaction: discord.Interaction,
                       member: discord.Member,
                       role: discord.Role,
                       duration: str):
        if not await self.check_command_permissions(interaction, 'temprole'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        try:
            end = datetime.datetime.utcnow().timestamp() + parse_time(duration)
        except ValueError:
            return await interaction.response.send_message("❌ Invalid duration format.", ephemeral=True)

        self.db.add_timed_action(
            guild_id=interaction.guild.id,
            action_type='temprole',
            end_ts=end,
            user_id=member.id,
            role_id=role.id,
        )
        await member.add_roles(role)
        await interaction.response.send_message(f"🎭 {role.name} → {member.mention} for {duration}")

    @app_commands.command(name="mute", description="Mute a member")
    @app_commands.describe(member="Member to mute", duration="Duration (e.g. 1h, 2d)", reason="Reason")
    async def mute(self, interaction: discord.Interaction,
                   member: discord.Member,
                   duration: str = None,
                   reason: str = "No reason provided"):
        if not await self.check_command_permissions(interaction, 'mute'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        if not await self.can_moderate_member(interaction, member):
            return await interaction.response.send_message("You cannot moderate this member as they are higher ranked.")

        mute_role_id = self.config.get('mute_role')
        role = interaction.guild.get_role(mute_role_id)
        if not role:
            return await interaction.response.send_message("❌ Mute role not configured.", ephemeral=True)

        # Validate duration BEFORE applying the mute
        end_ts = None
        if duration:
            try:
                end_ts = datetime.datetime.utcnow().timestamp() + parse_time(duration)
            except ValueError:
                return await interaction.response.send_message(
                    "❌ Invalid duration format. Use like 1h, 30m, 2d", ephemeral=True
                )

        await member.add_roles(role)
        try:
            await member.send(
                self.config['mute_message'].format(duration=duration or "indefinitely", reason=reason)
            )
        except (discord.Forbidden, KeyError):
            pass

        await interaction.response.send_message(f"🔇 Muted {member.mention}")
        await self.log(interaction, "Mute", member, reason, duration)

        if end_ts:
            self.db.add_timed_action(
                guild_id=interaction.guild.id,
                action_type='mute',
                end_ts=end_ts,
                user_id=member.id,
            )

    @app_commands.command(name="unmute", description="Unmute a member")
    @app_commands.describe(member="Member to unmute", reason="Reason")
    async def unmute(self, interaction: discord.Interaction,
                     member: discord.Member,
                     reason: str = "No reason provided"):
        if not await self.check_command_permissions(interaction, 'unmute'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        if not await self.can_moderate_member(interaction, member):
            return await interaction.response.send_message("You cannot moderate this member as they are higher ranked.")

        mute_role_id = self.config.get('mute_role')
        role = interaction.guild.get_role(mute_role_id)
        if not role:
            return await interaction.response.send_message("❌ Mute role not configured.", ephemeral=True)

        await member.remove_roles(role)
        try:
            await member.send(self.config['unmute_message'].format(reason=reason))
        except (discord.Forbidden, KeyError):
            pass

        await interaction.response.send_message(f"🔊 Unmuted {member.mention}")
        await self.log(interaction, "Unmute", member, reason)

    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.describe(member="Member to warn", reason="Reason")
    async def warn(self, interaction: discord.Interaction,
                   member: discord.Member,
                   reason: str = "No reason provided"):
        if not await self.check_command_permissions(interaction, 'warn'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        if not await self.can_moderate_member(interaction, member):
            return await interaction.response.send_message("You cannot moderate this member as they are higher ranked.")

        self.db.add_warning(
            guild_id=str(interaction.guild.id),
            user_id=str(member.id),
            reason=reason,
            moderator_id=interaction.user.id,
        )

        try:
            await member.send(self.config['warn_message'].format(reason=reason))
        except (discord.Forbidden, KeyError):
            pass

        await interaction.response.send_message(f"⚠️ Warned {member.mention}")
        await self.log(interaction, "Warn", member, reason)

    @app_commands.command(name="warnings", description="View warnings for a member")
    @app_commands.describe(member="Member to view warnings for")
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        if not await self.check_command_permissions(interaction, 'warnings'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        warns = self.db.get_warnings(str(interaction.guild.id), str(member.id))
        if not warns:
            return await interaction.response.send_message("✅ No warnings.")

        embed = discord.Embed(title=f"Warnings for {member}", color=discord.Color.orange())
        for i, w in enumerate(warns, 1):
            mod = interaction.guild.get_member(w["moderator_id"])
            embed.add_field(
                name=f"#{i}",
                value=f"{w['reason']} (by {mod or w['moderator_id']})",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="delwarn", description="Delete a warning from a member")
    @app_commands.describe(member="Member", index="Warning number to delete")
    async def delwarn(self, interaction: discord.Interaction,
                      member: discord.Member,
                      index: int):
        if not await self.check_command_permissions(interaction, 'delwarn'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        if not await self.can_moderate_member(interaction, member):
            return await interaction.response.send_message("You cannot moderate this member as they are higher ranked.")

        ok = self.db.delete_warning(str(interaction.guild.id), str(member.id), index)
        if ok:
            await interaction.response.send_message(f"🗑️ Deleted warning #{index}")
        else:
            await interaction.response.send_message("❌ Warning not found.", ephemeral=True)

    @app_commands.command(name="note", description="Add a note about a member")
    @app_commands.describe(member="Member", text="Note content")
    async def note(self, interaction: discord.Interaction, member: discord.Member, text: str):
        if not await self.check_command_permissions(interaction, 'note'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        self.db.add_note(
            guild_id=str(interaction.guild.id),
            user_id=str(member.id),
            note=text,
            moderator_id=interaction.user.id,
        )
        await interaction.response.send_message(f"📝 Note added for {member.mention}")

    @app_commands.command(name="notes", description="View notes for a member")
    @app_commands.describe(member="Member")
    async def notes(self, interaction: discord.Interaction, member: discord.Member):
        if not await self.check_command_permissions(interaction, 'notes'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        ns = self.db.get_notes(str(interaction.guild.id), str(member.id))
        if not ns:
            return await interaction.response.send_message("✅ No notes.")

        embed = discord.Embed(title=f"Notes for {member}", color=discord.Color.blue())
        for i, n in enumerate(ns, 1):
            mod = interaction.guild.get_member(n["moderator_id"])
            embed.add_field(
                name=f"#{i}",
                value=f"{n['note']} (by {mod or n['moderator_id']})",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="editnote", description="Edit a note about a member")
    @app_commands.describe(member="Member", index="Note number", text="New content")
    async def editnote(self, interaction: discord.Interaction,
                       member: discord.Member,
                       index: int,
                       text: str):
        if not await self.check_command_permissions(interaction, 'editnote'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        ok = self.db.edit_note(str(interaction.guild.id), str(member.id), index, text)
        if ok:
            await interaction.response.send_message(f"✏️ Edited note #{index}")
        else:
            await interaction.response.send_message("❌ Note not found.", ephemeral=True)

    @app_commands.command(name="delnote", description="Delete a note about a member")
    @app_commands.describe(member="Member", index="Note number")
    async def delnote(self, interaction: discord.Interaction,
                      member: discord.Member,
                      index: int):
        if not await self.check_command_permissions(interaction, 'delnote'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        ok = self.db.delete_note(str(interaction.guild.id), str(member.id), index)
        if ok:
            await interaction.response.send_message(f"🗑️ Deleted note #{index}")
        else:
            await interaction.response.send_message("❌ Note not found.", ephemeral=True)

    @app_commands.command(name="clearnotes", description="Delete all notes for a member")
    @app_commands.describe(member="Member")
    async def clearnotes(self, interaction: discord.Interaction, member: discord.Member):
        if not await self.check_command_permissions(interaction, 'clearnotes'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        self.db.clear_notes(str(interaction.guild.id), str(member.id))
        await interaction.response.send_message(f"🗑️ Cleared all notes for {member.mention}")

    @app_commands.command(name="modlogs", description="View moderation logs for a member")
    @app_commands.describe(member="Member", page="Page number (default 1)")
    async def modlogs(self, interaction: discord.Interaction,
                      member: discord.Member,
                      page: int = 1):
        if not await self.check_command_permissions(interaction, 'modlogs'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        logs = self.db.get_modlogs_for_user(str(interaction.guild.id), member.id, page)
        embed = discord.Embed(title=f"Modlogs for {member}", color=discord.Color.blue())
        for l in logs:
            embed.add_field(
                name=f"Case #{l['case_id']} – {l['action']}",
                value=f"Reason: {l['reason'] or 'None'}\nTime: {l['timestamp']}",
                inline=False,
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="case", description="View details of a specific case")
    @app_commands.describe(case_id="Case ID")
    async def case(self, interaction: discord.Interaction, case_id: int):
        if not await self.check_command_permissions(interaction, 'case'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        l = self.db.get_case(str(interaction.guild.id), case_id)
        if not l:
            return await interaction.response.send_message("❌ Case not found.", ephemeral=True)

        u = interaction.guild.get_member(l['user_id']) or l['user_id']
        m = interaction.guild.get_member(l['moderator_id']) or l['moderator_id']

        embed = discord.Embed(title=f"Case #{case_id}", color=discord.Color.purple())
        embed.add_field(name="Action",    value=l['action'],           inline=True)
        embed.add_field(name="User",      value=str(u),                inline=True)
        embed.add_field(name="Moderator", value=str(m),                inline=True)
        embed.add_field(name="Reason",    value=l['reason'] or "None", inline=False)

        # Calculate expiry from the stored action timestamp, not from now
        if l['duration']:
            try:
                action_time = datetime.datetime.fromisoformat(l['timestamp'])
                secs = parse_time(l['duration'])
                expiry = action_time + datetime.timedelta(seconds=secs)
                ts = int(expiry.timestamp())
                embed.add_field(name="Until", value=f"<t:{ts}:R> (<t:{ts}:F>)", inline=True)
            except ValueError:
                pass

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="ignored", description="List ignored users, roles, and channels")
    async def ignored(self, interaction: discord.Interaction):
        if not await self.check_command_permissions(interaction, 'ignored'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        ig = self.config.get('ignored', {})
        embed = discord.Embed(title="Ignored Entities", color=discord.Color.dark_grey())
        embed.add_field(name="Users",    value="\n".join([f"<@{u}>"  for u in ig.get('users',    [])]) or "None", inline=True)
        embed.add_field(name="Roles",    value="\n".join([f"<@&{r}>" for r in ig.get('roles',    [])]) or "None", inline=True)
        embed.add_field(name="Channels", value="\n".join([f"<#{c}>"  for c in ig.get('channels', [])]) or "None", inline=True)
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="reason", description="Update reason for a mod log case")
    @app_commands.describe(case_id="Case ID", reason="New reason")
    async def reason(self, interaction: discord.Interaction, case_id: int, reason: str):
        if not await self.check_command_permissions(interaction, 'reason'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        ok = self.db.update_case_reason(str(interaction.guild.id), case_id, reason)
        if ok:
            await interaction.response.send_message(f"✅ Updated reason for case {case_id}.")
        else:
            await interaction.response.send_message("❌ Case not found.", ephemeral=True)

    @app_commands.command(name="lock", description="Lock a text channel")
    async def lock(self, interaction: discord.Interaction,
                   channel: discord.TextChannel = None,
                   duration: str = None,
                   message: str = None):
        if not await self.check_command_permissions(interaction, 'lock'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        ch            = channel or interaction.channel
        everyone_perm = ch.permissions_for(interaction.guild.default_role)
        booster_role  = interaction.guild.get_role(self.config.get("booster_role_id"))
        booster_perm  = ch.permissions_for(booster_role) if booster_role else None

        if not (everyone_perm.send_messages or (booster_perm and booster_perm.send_messages)):
            return await interaction.response.send_message("❌ Channel is already locked or uneditable.", ephemeral=True)

        # Validate duration before locking
        end_ts = None
        if duration:
            try:
                end_ts = datetime.datetime.utcnow().timestamp() + parse_time(duration)
            except ValueError:
                return await interaction.response.send_message("❌ Invalid duration format.", ephemeral=True)

        await ch.set_permissions(
            interaction.guild.default_role,
            overwrite=discord.PermissionOverwrite(send_messages=False),
        )
        self.db.lock_channel(str(interaction.guild.id), ch.id)

        if message:
            await ch.send(message)

        await interaction.response.send_message(f"🔒 Locked {ch.mention}")

        if end_ts:
            self.db.add_timed_action(
                guild_id=interaction.guild.id,
                action_type='unlock_ch',
                end_ts=end_ts,
                channel_id=ch.id,
            )

    @app_commands.command(name="unlock", description="Unlock a previously locked channel")
    async def unlock(self, interaction: discord.Interaction,
                     channel: discord.TextChannel = None,
                     message: str = None):
        if not await self.check_command_permissions(interaction, 'unlock'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        ch = channel or interaction.channel

        if not self.db.is_channel_locked(str(interaction.guild.id), ch.id):
            return await interaction.response.send_message("❌ Channel is not locked by the bot.", ephemeral=True)

        await ch.set_permissions(
            interaction.guild.default_role,
            overwrite=discord.PermissionOverwrite(send_messages=True),
        )
        self.db.unlock_channel(str(interaction.guild.id), ch.id)

        if message:
            await ch.send(message)

        await interaction.response.send_message(f"🔓 Unlocked {ch.mention}")

    lockdown = app_commands.Group(name="lockdown", description="Server lockdown controls")

    @lockdown.command(name="start", description="Lock all text channels (except excluded)")
    async def lockdown_start(self, interaction: discord.Interaction, message: str = None):
        if not await self.check_command_permissions(interaction, 'lockdown'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        excluded_ch  = set(self.config.get("lockdown_channels_exclude", []))
        excluded_cat = set(self.config.get("lockdown_categories_exclude", []))
        locked_count = 0

        for ch in interaction.guild.text_channels:
            if ch.id in excluded_ch or (ch.category_id and ch.category_id in excluded_cat):
                continue
            if ch.permissions_for(interaction.guild.default_role).send_messages:
                await ch.set_permissions(
                    interaction.guild.default_role,
                    overwrite=discord.PermissionOverwrite(send_messages=False),
                )
                self.db.lock_channel(str(interaction.guild.id), ch.id)
                locked_count += 1
                if message:
                    await ch.send(message)

        await interaction.response.send_message(
            f"🔒 Server lockdown started. Locked {locked_count} channels."
        )

    @lockdown.command(name="end", description="End server lockdown and unlock affected channels")
    async def lockdown_end(self, interaction: discord.Interaction, message: str = None):
        if not await self.check_command_permissions(interaction, 'lockdown'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        locked_ids = self.db.get_locked_channels(str(interaction.guild.id))
        unlocked   = 0

        for ch_id in locked_ids:
            ch = interaction.guild.get_channel(ch_id)
            if ch:
                await ch.set_permissions(
                    interaction.guild.default_role,
                    overwrite=discord.PermissionOverwrite(send_messages=True),
                )
                if message:
                    await ch.send(message)
                unlocked += 1

        self.db.clear_locked_channels(str(interaction.guild.id))
        await interaction.response.send_message(f"🔓 Lockdown ended. Unlocked {unlocked} channels.")

    @app_commands.command(name="moderations", description="View active moderations for a member")
    @app_commands.describe(member="Member to check", page="Page (default 1)")
    async def moderations(self, interaction: discord.Interaction,
                          member: discord.Member,
                          page: int = 1):
        if not await self.check_command_permissions(interaction, 'moderations'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        all_actions = self.sql.fetchall(
            "SELECT * FROM timed_actions WHERE guild_id = ? AND user_id = ? ORDER BY end_ts",
            (interaction.guild.id, member.id),
        )
        pag = all_actions[(page - 1) * 5: page * 5]

        embed = discord.Embed(title=f"Active moderations for {member}", color=discord.Color.green())
        for t in pag:
            embed.add_field(
                name=t['type'].title(),
                value=f"Ends <t:{int(t['end_ts'])}:R>",
                inline=False,
            )
        if not embed.fields:
            embed.description = "No active moderations"

        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="modstats", description="View moderation statistics for a moderator")
    @app_commands.describe(member="Moderator to view stats for")
    async def modstats(self, interaction: discord.Interaction, member: discord.Member):
        if not await self.check_command_permissions(interaction, 'modstats'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        rows = self.db.get_modstats(str(interaction.guild.id), member.id)
        if not rows:
            return await interaction.response.send_message(
                f"📊 No moderation actions found for {member.mention}"
            )

        total = sum(r["cnt"] for r in rows)
        embed = discord.Embed(title=f"Moderation Stats for {member}", color=discord.Color.blurple())
        for r in rows:
            embed.add_field(name=r["action"], value=str(r["cnt"]), inline=True)
        embed.set_footer(text=f"Total actions: {total}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="duration", description="Change duration of a timed moderation")
    @app_commands.describe(case_id="Case ID", limit="New duration (e.g. 1h, 2d)")
    async def duration(self, interaction: discord.Interaction, case_id: int, limit: str):
        if not await self.check_command_permissions(interaction, 'duration'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        ok = self.db.update_case_duration(str(interaction.guild.id), case_id, limit)
        if not ok:
            return await interaction.response.send_message("❌ Case not found or not timed.", ephemeral=True)

        l = self.db.get_case(str(interaction.guild.id), case_id)
        try:
            new_end = datetime.datetime.utcnow().timestamp() + parse_time(limit)
            self.db.update_timed_action_end(
                guild_id=interaction.guild.id,
                action_type=l['action'].lower(),
                user_id=l['user_id'],
                new_end=new_end,
            )
            await interaction.response.send_message(f"✅ Updated duration for case {case_id} to {limit}")
        except ValueError:
            await interaction.response.send_message("❌ Invalid duration format.", ephemeral=True)

    @app_commands.command(name="fireboard", description="View fireboard stats for a message")
    @app_commands.describe(link="Message link to check")
    async def fireboard(self, interaction: discord.Interaction, link: str):
        if not await self.check_command_permissions(interaction, 'fireboard'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        try:
            parts      = link.split('/')
            message_id = int(parts[-1])
            channel_id = int(parts[-2])

            channel = interaction.guild.get_channel(channel_id)
            if not channel:
                return await interaction.response.send_message("❌ Channel not found.", ephemeral=True)

            message = await channel.fetch_message(message_id)
            embed   = discord.Embed(
                title="Fireboard Stats",
                description=f"Stats for [this message]({link})",
                color=discord.Color.orange(),
            )
            embed.add_field(name="🔥 Reactions", value=str(len(message.reactions)))
            embed.add_field(name="💬 Replies",   value="Not tracked")
            await interaction.response.send_message(embed=embed)

        except (IndexError, ValueError, discord.NotFound, discord.Forbidden):
            await interaction.response.send_message(
                "❌ Invalid message link or unable to fetch message.", ephemeral=True
            )


async def setup(bot):
    await bot.add_cog(Moderation(bot))