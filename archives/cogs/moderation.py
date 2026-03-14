import discord
from discord import app_commands
from discord.ext import commands, tasks
import datetime
from utils.data_handler import DataHandler
from utils.config_manager import ConfigManager
import asyncio

class Moderation(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        # Data and config
        self.data_handler = DataHandler('data/moderation.json')
        self.data = self.data_handler.load_data()
        self.config_manager = ConfigManager('config.json')
        self.config = self.config_manager.load_config().get('moderation', {})
        
        # Command configs (permissions & roles from config.json)
        self.command_configs = {
            'deafen':       {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['deafen_members']},
            'undeafen':     {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['deafen_members']},
            'kick':         {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['kick_members']},
            'ban':          {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['ban_members']},
            'unban':        {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['ban_members']},
            'softban':      {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['ban_members']},
            'mute':         {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_roles']},
            'unmute':       {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_roles']},
            'members':      {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'rolepersist':  {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_roles']},
            'temprole':     {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_roles']},
            'warn':         {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['kick_members']},
            'warnings':     {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'delwarn':      {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['kick_members']},
            'note':         {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['kick_members']},
            'notes':        {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'editnote':     {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['kick_members']},
            'delnote':      {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['kick_members']},
            'clearnotes':   {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['kick_members']},
            'modlogs':      {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'case':         {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'moderations':  {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'lock':         {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_channels']},
            'unlock':       {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_channels']},
            'lockdown':     {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_channels']},
            'ignored':      {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'reason':       {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['kick_members']},
            'modstats':     {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'duration':     {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['kick_members']},
            'clean':        {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_messages']},
            'fireboard':    {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
        }
        self.update_configs()
        # start background loop
        self._timed_loop.start()

    def update_configs(self):
        if 'commands' in self.config:
            for cmd, cfg in self.config['commands'].items():
                if cmd in self.command_configs:
                    self.command_configs[cmd].update(cfg)

    async def check_command_permissions(self, interaction: discord.Interaction, command_name):
        cfg = self.command_configs.get(command_name, {})
        if not cfg.get('enabled', True):
            return False
        # role check
        req = cfg.get('required_roles', [])
        if req and '@everyone' not in req:
            user_roles = [str(r.id) for r in interaction.user.roles]
            if not any(rid in user_roles for rid in req):
                return False
        # perms check
        for p in cfg.get('permissions', []):
            if not getattr(interaction.user.guild_permissions, p, False):
                return False
        return True

    async def can_moderate_member(self, interaction, member):
        """
        Check if the user can moderate the specified member.
        This function checks role hierarchy and allows self-muting.
        It also excludes the muted role from the comparison.
        """
        muted_role_id = self.config.get('mute_role')  # Get muted role ID from the config
        muted_role = interaction.guild.get_role(muted_role_id)

        # Get the highest role of the user and the member
        user_top_role = interaction.user.top_role
        member_top_role = member.top_role

        # Exclude the muted role from the top role comparison if it's present
        if muted_role in interaction.user.roles:
            user_top_role = sorted([role for role in interaction.user.roles if role != muted_role], key=lambda role: role.position, reverse=True)[0]
        if muted_role in member.roles:
            member_top_role = sorted([role for role in member.roles if role != muted_role], key=lambda role: role.position, reverse=True)[0]

        # Allow the user to mute themselves regardless of role comparison
        if interaction.user == member:
            return True  # Allow self-muting
    
        # Check if the user's top role is lower than or equal to the member's top role
        if user_top_role <= member_top_role:
            return False  # User cannot moderate the member

        return True  # User can moderate the member

    # background loop to handle timed actions
    @tasks.loop(seconds=30)
    async def _timed_loop(self):
        now = datetime.datetime.utcnow().timestamp()
        new = []
        for action in self.data.get('timed', []):
            if now >= action.get('end', 0):
                guild = self.bot.get_guild(action.get('guild_id'))
                if not guild:
                    continue

                user_id = action.get('user_id')
                action_type = action.get('type')

                # Only act if the action needs a user_id and it's present
                if action_type in ['ban', 'mute', 'temprole'] and user_id is None:
                    continue

                try:
                    if action_type == 'ban':
                        await guild.unban(discord.Object(id=user_id))
                    elif action_type == 'mute':
                        member = guild.get_member(user_id)
                        role = guild.get_role(int(self.config['mute_role']))
                        if member and role:
                            await member.remove_roles(role)
                            await member.send(self.config['unmute_message'].format(reason='Time expired'))
                    elif action_type == 'temprole':
                        member = guild.get_member(user_id)
                        role = guild.get_role(action.get('role_id'))
                        if member and role:
                            await member.remove_roles(role)
                    elif action_type == 'unlock_ch':
                        channel = guild.get_channel(action.get('channel_id'))
                        if channel:
                            await channel.set_permissions(guild.default_role, send_messages=True)
                except Exception as e:
                    print(f"Error handling action {action}: {e}")
            else:
                new.append(action)
        self.data['timed'] = new
        self.data_handler.save_data(self.data)

    @commands.Cog.listener()
    async def on_member_join(self, member):
        gid, uid = str(member.guild.id), str(member.id)
        for rid in self.data.get('persisted_roles', {}).get(gid, {}).get(uid, []):
            role = member.guild.get_role(rid)
            if role:
                await member.add_roles(role)

    # --- COMMANDS ---

    @app_commands.command(name="clean", description="Clean up the bot's responses")
    @app_commands.describe(amount="Number of messages to clean (default 10)")
    async def clean(self, interaction: discord.Interaction, amount: int = 10):
        """Clean up the bot's responses."""
        if not await self.check_command_permissions(interaction, 'clean'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
    
        await interaction.response.defer(ephemeral=True)

        def is_bot(m): return m.author == self.bot.user
        deleted = await interaction.channel.purge(limit=1000, check=is_bot)
        count = min(len(deleted), amount)

        # Send the followup message
        message = await interaction.followup.send(
            self.config.get('clean_message', f"Deleted {count} messages."),
            ephemeral=True
        )

        # ❗️Manually delete it after 5 seconds
        await asyncio.sleep(5)
        await message.delete()


    @app_commands.command(name="deafen", description="Deafen a member in voice channel")
    @app_commands.describe(member="Member to deafen")
    async def deafen(self, interaction: discord.Interaction, member: discord.Member):
        """Deafen a member."""
        if not await self.check_command_permissions(interaction, 'deafen'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        await member.edit(deafen=True)
        await interaction.response.send_message(f"🔇 Deafened {member.mention}")

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

    @app_commands.command(name="undeafen", description="Undeafen a member in voice channel")
    @app_commands.describe(member="Member to undeafen")
    async def undeafen(self, interaction: discord.Interaction, member: discord.Member):
        """Undeafen a member."""
        if not await self.check_command_permissions(interaction, 'undeafen'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        if not await self.can_moderate_member(interaction, member):
            await interaction.response.send_message("You cannot moderate this member as they are higher ranked.")
            return

        await member.edit(deafen=False)
        await interaction.response.send_message(f"🔊 Undeafened {member.mention}")

    @app_commands.command(name="kick", description="Kick a member from the server")
    @app_commands.describe(
        member="Member to kick",
        reason="Reason for kick"
    )
    async def kick(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        """Kick a member."""
        if not await self.check_command_permissions(interaction, 'kick'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        if not await self.can_moderate_member(interaction, member):
            await interaction.response.send_message("You cannot moderate this member as they are higher ranked.")
            return

        dm = self.config['kick_message'].format(reason=reason)
        try:
            await member.send(dm)
        except discord.Forbidden:
            pass
        await member.kick(reason=reason)
        await interaction.response.send_message(f"👢 Kicked {member.mention}")
        await self.log(interaction, "Kick", member, reason)

    @app_commands.command(name="ban", description="Ban a member from the server")
    @app_commands.describe(
        member="Member to ban",
        duration="Duration of ban (e.g. 1d, 2h)",
        reason="Reason for ban"
    )
    async def ban(self, interaction: discord.Interaction, member: discord.Member, duration: str = None, reason: str = "No reason provided"):
        """Ban a member, optionally timed."""
        if not await self.check_command_permissions(interaction, 'ban'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        if not await self.can_moderate_member(interaction, member):
            await interaction.response.send_message("You cannot moderate this member as they are higher ranked.")
            return

        dm = self.config['ban_message'].format(duration=duration or "permanently", reason=reason)
        try:
            await member.send(dm)
        except discord.Forbidden:
            pass
        await member.ban(reason=reason)
        await interaction.response.send_message(f"🔨 Banned {member.mention}")
        await self.log(interaction, "Ban", member, reason, duration)
        if duration:
            end = datetime.datetime.utcnow().timestamp() + parse_time(duration)
            self.data.setdefault('timed', []).append({
                'type':'ban','user_id':member.id,
                'guild_id':interaction.guild.id,'end':end
            })
            self.data_handler.save_data(self.data)

    @app_commands.command(name="unban", description="Unban a user from the server")
    @app_commands.describe(
        user_id="ID of user to unban",
        reason="Reason for unban"
    )
    async def unban(self, interaction: discord.Interaction, user_id: str, reason: str = "No reason provided"):
        """Unban a member."""
        if not await self.check_command_permissions(interaction, 'unban'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        try:
            user_id = int(user_id)
        except ValueError:
            return await interaction.response.send_message("❌ Invalid user ID format.", ephemeral=True)
            
        user = discord.Object(id=user_id)
        try:
            await interaction.guild.unban(user, reason=reason)
            await interaction.response.send_message(f"🔓 Unbanned user {user_id}")
            await self.log(interaction, "Unban", user, reason)
        except discord.NotFound:
            await interaction.response.send_message("❌ User is not banned.", ephemeral=True)

    @app_commands.command(name="softban", description="Softban a member (kick with message deletion)")
    @app_commands.describe(
        member="Member to softban",
        reason="Reason for softban"
    )
    async def softban(self, interaction: discord.Interaction, member: discord.Member, reason: str = "No reason provided"):
        """Softban a member."""
        if not await self.check_command_permissions(interaction, 'softban'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        if not await self.can_moderate_member(interaction, member):
            await interaction.response.send_message("You cannot moderate this member as they are higher ranked.")
            return

        await member.ban(reason=reason, delete_message_days=7)
        await interaction.guild.unban(member)
        await interaction.response.send_message(f"🛑 Softbanned {member.mention}")
        await self.log(interaction, "Softban", member, reason)

    @app_commands.command(name="members", description="List members in specified roles")
    @app_commands.describe(roles="Roles to check (mention or ID)")
    async def members(self, interaction: discord.Interaction, roles: str):
        """List members in specified role(s) with member count"""
        if not await self.check_command_permissions(interaction, 'members'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
    
        # Parse role mentions/IDs from the input string
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
                "❌ No valid roles provided. Mention roles or use their IDs.",
                ephemeral=True
            )
    
        # Get unique members from all specified roles (max 5 roles)
        unique_members = set()
        for role in role_objects[:5]:
            unique_members.update(role.members)
    
        member_count = len(unique_members)
        mentions = [m.mention for m in list(unique_members)[:90]]  # Still limit mentions to 90
    
        # Create the response message
        response_parts = [
            f"**Found {member_count} members in specified roles:**",
            ""
        ]
    
        if mentions:
            response_parts.append(", ".join(mentions))
        else:
            response_parts.append("No members found in these roles.")
    
        # Add role names for clarity
        role_names = ", ".join(f"'{r.name}'" for r in role_objects[:5])
        if len(role_objects) > 5:
            role_names += f" (and {len(role_objects)-5} more)"
        response_parts.append(f"\n*Roles checked: {role_names}*")
    
        await interaction.response.send_message(
            "\n".join(response_parts),
            ephemeral=True
        )

    # @app_commands.command(name="rolepersist", description="Manage persistent roles")
    # @app_commands.describe(
    #     action="Action to perform",
    #     member="Member to affect",
    #     role="Role to persist"
    # )
    # @app_commands.choices(action=[
    #     app_commands.Choice(name="add", value="add"),
    #     app_commands.Choice(name="remove", value="remove"),
    #     app_commands.Choice(name="toggle", value="toggle"),
    # ])
    # async def rolepersist(self, interaction: discord.Interaction, 
    #                      action: app_commands.Choice[str], 
    #                      member: discord.Member, 
    #                      role: discord.Role):
    #     """Add/remove/toggle a persistent role."""
    #     if not await self.check_command_permissions(interaction, 'rolepersist'):
    #         return await interaction.response.send_message("❌ No permission.", ephemeral=True)
        
    #     gid, uid = str(interaction.guild.id), str(member.id)
    #     pr = self.data.setdefault('persisted_roles', {}).setdefault(gid, {})
    #     lst = pr.setdefault(uid, [])
        
    #     action_value = action.value
    #     if action_value == 'add' and role.id not in lst:
    #         lst.append(role.id)
    #         await member.add_roles(role)
    #     elif action_value == 'remove' and role.id in lst:
    #         lst.remove(role.id)
    #         await member.remove_roles(role)
    #     elif action_value == 'toggle':
    #         if role.id in lst:
    #             lst.remove(role.id)
    #             await member.remove_roles(role)
    #         else:
    #             lst.append(role.id)
    #             await member.add_roles(role)
                
    #     self.data_handler.save_data(self.data)  # Save the updated data
    #     await interaction.response.send_message(f"✅ {action_value.title()}ed {role.name} for {member.mention}")

    # /announce command
    @app_commands.command(name="announce", description="Send an announcement with markdown formatting.")
    async def announce(self, interaction: discord.Interaction, content: str, channel: discord.TextChannel = None):
        """Send an announcement message with Markdown formatting and new lines."""
        # Replace \n with an actual newline character for multi-line messages
        content = content.replace("\\n", "\n")

        # Default to the current channel if no channel is specified
        channel = channel or interaction.channel
        
        # Send the message with markdown rendering
        await channel.send(content)
        
        # Acknowledge the interaction
        await interaction.response.send_message(f"Announcement sent in {channel.mention}!", ephemeral=True)

    @app_commands.command(name="temprole", description="Assign a temporary role")
    @app_commands.describe(
        member="Member to assign role to",
        role="Role to assign",
        duration="Duration (e.g. 1h, 2d)"
    )
    async def temprole(self, interaction: discord.Interaction, 
                      member: discord.Member, 
                      role: discord.Role, 
                      duration: str):
        """Assign a role for a limited time."""
        if not await self.check_command_permissions(interaction, 'temprole'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
            
        try:
            end = datetime.datetime.utcnow().timestamp() + parse_time(duration)
        except ValueError:
            return await interaction.response.send_message("❌ Invalid duration format. Use like 1h, 30m, 2d", ephemeral=True)
            
        self.data.setdefault('timed',[]).append({
            'type':'temprole',
            'user_id':member.id,
            'guild_id':interaction.guild.id,
            'role_id':role.id,
            'end':end
        })
        self.data_handler.save_data(self.data)
        await member.add_roles(role)
        await interaction.response.send_message(f"🎭 {role.name} -> {member.mention} for {duration}")

    @app_commands.command(name="mute", description="Mute a member")
    @app_commands.describe(
        member="Member to mute",
        duration="Duration of mute (e.g. 1h, 2d)",
        reason="Reason for mute"
    )
    async def mute(self, interaction: discord.Interaction, 
                  member: discord.Member, 
                  duration: str = None, 
                  reason: str = "No reason provided"):
        """Mute a member so they cannot type."""
        if not await self.check_command_permissions(interaction, 'mute'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        if not await self.can_moderate_member(interaction, member):
            await interaction.response.send_message("You cannot moderate this member as they are higher ranked.")
            return
            
        mute_role_id = self.config.get('mute_role')
        role = interaction.guild.get_role(mute_role_id)  # Fetch the role by ID
        if not role:
            return await interaction.response.send_message("❌ Mute role not configured.", ephemeral=True)
            
        await member.add_roles(role)
        dm = self.config['mute_message'].format(duration=duration or "indefinitely", reason=reason)
        try:
            await member.send(dm)
        except discord.Forbidden:
            pass
            
        await interaction.response.send_message(f"🔇 Muted {member.mention}")
        await self.log(interaction, "Mute", member, reason, duration)
        
        if duration:
            try:
                end = datetime.datetime.utcnow().timestamp() + parse_time(duration)
                self.data.setdefault('timed', []).append({
                    'type':'mute',
                    'user_id':member.id,
                    'guild_id':interaction.guild.id,
                    'end':end
                })
                self.data_handler.save_data(self.data)
            except ValueError:
                pass

    @app_commands.command(name="unmute", description="Unmute a member")
    @app_commands.describe(
        member="Member to unmute",
        reason="Reason for unmute"
    )
    async def unmute(self, interaction: discord.Interaction, 
                    member: discord.Member, 
                    reason: str = "No reason provided"):
        """Unmute a member."""
        if not await self.check_command_permissions(interaction, 'unmute'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        if not await self.can_moderate_member(interaction, member):
            await interaction.response.send_message("You cannot moderate this member as they are higher ranked.")
            return
            
        mute_role_id = self.config.get('mute_role')
        role = interaction.guild.get_role(mute_role_id)  # Fetch the role by ID
        if not role:
            return await interaction.response.send_message("❌ Mute role not configured.", ephemeral=True)
            
        await member.remove_roles(role)
        dm = self.config['unmute_message'].format(reason=reason)
        try:
            await member.send(dm)
        except discord.Forbidden:
            pass
            
        await interaction.response.send_message(f"🔊 Unmuted {member.mention}")
        await self.log(interaction, "Unmute", member, reason)

    @app_commands.command(name="warn", description="Warn a member")
    @app_commands.describe(
        member="Member to warn",
        reason="Reason for warning"
    )
    async def warn(self, interaction: discord.Interaction, 
                  member: discord.Member, 
                  reason: str = "No reason provided"):
        """Warn a member."""
        if not await self.check_command_permissions(interaction, 'warn'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        if not await self.can_moderate_member(interaction, member):
            await interaction.response.send_message("You cannot moderate this member as they are higher ranked.")
            return
            
        gid, uid = str(interaction.guild.id), str(member.id)
        self.data.setdefault('warnings',{}).setdefault(gid,{}).setdefault(uid,[]).append({
            'reason':reason,
            'mod':interaction.user.id,
            'time':datetime.datetime.utcnow().isoformat()
        })
        self.data_handler.save_data(self.data)
        
        dm = self.config['warn_message'].format(reason=reason)
        try:
            await member.send(dm)
        except discord.Forbidden:
            pass
            
        await interaction.response.send_message(f"⚠️ Warned {member.mention}")
        await self.log(interaction, "Warn", member, reason)

    @app_commands.command(name="warnings", description="View warnings for a member")
    @app_commands.describe(member="Member to view warnings for")
    async def warnings(self, interaction: discord.Interaction, member: discord.Member):
        """Get warnings for a user."""
        if not await self.check_command_permissions(interaction, 'warnings'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
            
        warns = self.data.get('warnings',{}).get(str(interaction.guild.id),{}).get(str(member.id),[])
        if not warns:
            return await interaction.response.send_message("✅ No warnings.")
            
        embed = discord.Embed(title=f"Warnings for {member}", color=discord.Color.orange())
        for i, w in enumerate(warns, 1):
            mod = interaction.guild.get_member(w['mod'])
            embed.add_field(
                name=f"#{i}",
                value=f"{w['reason']} (by {mod or w['mod']})",
                inline=False
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="delwarn", description="Delete a warning from a member")
    @app_commands.describe(
        member="Member to remove warning from",
        index="Warning number to delete"
    )
    async def delwarn(self, interaction: discord.Interaction, 
                     member: discord.Member, 
                     index: int):
        """Delete a warning."""
        if not await self.check_command_permissions(interaction, 'delwarn'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        if not await self.can_moderate_member(interaction, member):
            await interaction.response.send_message("You cannot moderate this member as they are higher ranked.")
            return
            
        gw = self.data.get('warnings',{}).get(str(interaction.guild.id),{})
        uw = gw.get(str(member.id),[])
        
        if 1 <= index <= len(uw):
            uw.pop(index-1)
            self.data_handler.save_data(self.data)
            await interaction.response.send_message(f"🗑️ Deleted warning #{index}")
        else:
            await interaction.response.send_message("❌ Warning not found.", ephemeral=True)

    @app_commands.command(name="note", description="Add a note about a member")
    @app_commands.describe(
        member="Member to add note about",
        text="Note content"
    )
    async def note(self, interaction: discord.Interaction, 
                  member: discord.Member, 
                  text: str):
        """Add a note about a member."""
        if not await self.check_command_permissions(interaction, 'note'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
            
        gid, uid = str(interaction.guild.id), str(member.id)
        self.data.setdefault('notes',{}).setdefault(gid,{}).setdefault(uid,[]).append({
            'note':text,
            'mod':interaction.user.id,
            'time':datetime.datetime.utcnow().isoformat()
        })
        self.data_handler.save_data(self.data)
        await interaction.response.send_message(f"📝 Note added for {member.mention}")

    @app_commands.command(name="notes", description="View notes for a member")
    @app_commands.describe(member="Member to view notes for")
    async def notes(self, interaction: discord.Interaction, member: discord.Member):
        """Get notes for a user."""
        if not await self.check_command_permissions(interaction, 'notes'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
            
        ns = self.data.get('notes',{}).get(str(interaction.guild.id),{}).get(str(member.id),[])
        if not ns:
            return await interaction.response.send_message("✅ No notes.")
            
        embed = discord.Embed(title=f"Notes for {member}", color=discord.Color.blue())
        for i, n in enumerate(ns, 1):
            mod = interaction.guild.get_member(n['mod'])
            embed.add_field(
                name=f"#{i}",
                value=f"{n['note']} (by {mod or n['mod']})",
                inline=False
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="editnote", description="Edit a note about a member")
    @app_commands.describe(
        member="Member whose note to edit",
        index="Note number to edit",
        text="New note content"
    )
    async def editnote(self, interaction: discord.Interaction, 
                      member: discord.Member, 
                      index: int, 
                      text: str):
        """Edit a note about a member."""
        if not await self.check_command_permissions(interaction, 'editnote'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
            
        ns = self.data.get('notes',{}).get(str(interaction.guild.id),{}).get(str(member.id),[])
        if 1 <= index <= len(ns):
            ns[index-1]['note'] = text
            self.data_handler.save_data(self.data)
            await interaction.response.send_message(f"✏️ Edited note #{index}")
        else:
            await interaction.response.send_message("❌ Note not found.", ephemeral=True)

    @app_commands.command(name="delnote", description="Delete a note about a member")
    @app_commands.describe(
        member="Member whose note to delete",
        index="Note number to delete"
    )
    async def delnote(self, interaction: discord.Interaction, 
                     member: discord.Member, 
                     index: int):
        """Delete a note about a member."""
        if not await self.check_command_permissions(interaction, 'delnote'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
            
        ns = self.data.get('notes',{}).get(str(interaction.guild.id),{}).get(str(member.id),[])
        if 1 <= index <= len(ns):
            ns.pop(index-1)
            self.data_handler.save_data(self.data)
            await interaction.response.send_message(f"🗑️ Deleted note #{index}")
        else:
            await interaction.response.send_message("❌ Note not found.", ephemeral=True)

    @app_commands.command(name="clearnotes", description="Delete all notes for a member")
    @app_commands.describe(member="Member to clear notes for")
    async def clearnotes(self, interaction: discord.Interaction, member: discord.Member):
        """Delete all notes for a member."""
        if not await self.check_command_permissions(interaction, 'clearnotes'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
            
        self.data.get('notes',{}).get(str(interaction.guild.id),{}).pop(str(member.id), None)
        self.data_handler.save_data(self.data)
        await interaction.response.send_message(f"🗑️ Cleared all notes for {member.mention}")

    @app_commands.command(name="modlogs", description="View moderation logs for a member")
    @app_commands.describe(
        member="Member to view logs for",
        page="Page number (default 1)"
    )
    async def modlogs(self, interaction: discord.Interaction, 
                     member: discord.Member, 
                     page: int = 1):
        """Get a list of moderation logs for a user."""
        if not await self.check_command_permissions(interaction, 'modlogs'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
            
        logs = self.data.get('modlogs', {}).get(str(interaction.guild.id), [])
        user_logs = [l for l in logs if l['user_id']==member.id]
        start, end = (page-1)*5, page*5
        
        embed = discord.Embed(title=f"Modlogs for {member}", color=discord.Color.blue())
        for l in user_logs[start:end]:
            embed.add_field(
                name=f"Case #{l['case_id']} – {l['action']}",
                value=f"Reason: {l['reason'] or 'None'}\nTime: {l['timestamp']}",
                inline=False
            )
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="case", description="View details of a specific case")
    @app_commands.describe(case_id="Case ID to view")
    async def case(self, interaction: discord.Interaction, case_id: int):
        """Show a single mod log case."""
        if not await self.check_command_permissions(interaction, 'case'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
            
        logs = self.data.get('modlogs', {}).get(str(interaction.guild.id), [])
        for l in logs:
            if l['case_id']==case_id:
                u = interaction.guild.get_member(l['user_id']) or l['user_id']
                m = interaction.guild.get_member(l['moderator_id']) or l['moderator_id']
                
                embed = discord.Embed(title=f"Case #{case_id}", color=discord.Color.purple())
                embed.add_field(name="Action", value=l['action'], inline=True)
                embed.add_field(name="User", value=u, inline=True)
                embed.add_field(name="Moderator", value=m, inline=True)
                embed.add_field(name="Reason", value=l['reason'] or "None", inline=False)
                
                if l['duration']:
                    try:
                        secs = parse_time(l['duration'])
                        ts = int((datetime.datetime.utcnow()+datetime.timedelta(seconds=secs)).timestamp())
                        embed.add_field(name="Until", value=f"<t:{ts}:R> (<t:{ts}:F>)", inline=True)
                    except ValueError:
                        pass
                        
                return await interaction.response.send_message(embed=embed)
                
        await interaction.response.send_message("❌ Case not found.", ephemeral=True)

    @app_commands.command(name="ignored", description="List ignored users, roles, and channels")
    async def ignored(self, interaction: discord.Interaction):
        """List ignored users, roles, and channels."""
        if not await self.check_command_permissions(interaction, 'ignored'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
            
        ig = self.data.get('ignored', {})
        embed = discord.Embed(title="Ignored Entities", color=discord.Color.dark_grey())
        embed.add_field(name="Users", value="\n".join([f"<@{uid}>" for uid in ig.get('users', [])]) or "None", inline=True)
        embed.add_field(name="Roles", value="\n".join([f"<@&{rid}>" for rid in ig.get('roles', [])]) or "None", inline=True)
        embed.add_field(name="Channels", value="\n".join([f"<#{cid}>" for cid in ig.get('channels', [])]) or "None", inline=True)
        
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="reason", description="Update reason for a mod log case")
    @app_commands.describe(
        case_id="Case ID to update",
        reason="New reason"
    )
    async def reason(self, interaction: discord.Interaction, case_id: int, reason: str):
        """Supply a reason for a mod log case."""
        if not await self.check_command_permissions(interaction, 'reason'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
            
        logs = self.data.get('modlogs', {}).get(str(interaction.guild.id), [])
        for l in logs:
            if l['case_id']==case_id:
                l['reason'] = reason
                self.data_handler.save_data(self.data)
                return await interaction.response.send_message(f"✅ Updated reason for case {case_id}.")
                
        await interaction.response.send_message("❌ Case not found.", ephemeral=True)

    ########################
    # Lock Channel Command #
    ########################
    @app_commands.command(name="lock", description="Lock a text channel")
    async def lock(self, interaction: discord.Interaction, 
                   channel: discord.TextChannel = None, 
                   duration: str = None, 
                   message: str = None):
        if not await self.check_command_permissions(interaction, 'lock'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        ch = channel or interaction.channel
        everyone_perm = ch.permissions_for(interaction.guild.default_role)
        booster_role = interaction.guild.get_role(self.config.get("booster_role_id"))
        booster_perm = ch.permissions_for(booster_role) if booster_role else None

        if not (everyone_perm.send_messages or (booster_perm and booster_perm.send_messages)):
            return await interaction.response.send_message("❌ Channel is already locked or uneditable.", ephemeral=True)

        await ch.set_permissions(interaction.guild.default_role, overwrite=discord.PermissionOverwrite(send_messages=False))
        self.data.setdefault('locked_channels', set()).add(ch.id)
        if message:
            await ch.send(message)

        await interaction.response.send_message(f"🔒 Locked {ch.mention}")

        if duration:
            try:
                end = datetime.datetime.utcnow().timestamp() + parse_time(duration)
                self.data.setdefault('timed', []).append({
                    'type': 'unlock_ch',
                    'guild_id': interaction.guild.id,
                    'channel_id': ch.id,
                    'end': end
                })
                self.data_handler.save_data(self.data)
            except ValueError:
                await interaction.followup.send("⚠️ Invalid duration format.")

    ##########################
    # Unlock Channel Command #
    ##########################
    @app_commands.command(name="unlock", description="Unlock a previously locked channel")
    async def unlock(self, interaction: discord.Interaction, 
                     channel: discord.TextChannel = None, 
                     message: str = None):
        if not await self.check_command_permissions(interaction, 'unlock'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        ch = channel or interaction.channel
        locked = self.data.get("locked_channels", set())

        if ch.id not in locked:
            return await interaction.response.send_message("❌ Channel is not locked by the bot.", ephemeral=True)

        await ch.set_permissions(interaction.guild.default_role, overwrite=discord.PermissionOverwrite(send_messages=True))
        locked.discard(ch.id)

        if message:
            await ch.send(message)

        await interaction.response.send_message(f"🔓 Unlocked {ch.mention}")
        self.data_handler.save_data(self.data)

    ###################################
    # Lockdown Group (/lockdown ...)  #
    ###################################
    lockdown = app_commands.Group(name="lockdown", description="Server lockdown controls")

    @lockdown.command(name="start", description="Lock all text channels (except excluded)")
    async def lockdown_start(self, interaction: discord.Interaction, message: str = None):
        if not await self.check_command_permissions(interaction, 'lockdown'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        locked = []
        excluded_ch = set(self.config.get("lockdown_channels_exclude", []))
        excluded_cat = set(self.config.get("lockdown_categories_exclude", []))

        for ch in interaction.guild.text_channels:
            if ch.id in excluded_ch or (ch.category_id and ch.category_id in excluded_cat):
                continue

            perms = ch.permissions_for(interaction.guild.default_role)
            if perms.send_messages:
                await ch.set_permissions(interaction.guild.default_role, overwrite=discord.PermissionOverwrite(send_messages=False))
                locked.append(ch.id)
                if message:
                    await ch.send(message)

        self.data["lockdown_active"] = True
        self.data["locked_channels"] = set(locked)
        self.data_handler.save_data(self.data)

        await interaction.response.send_message(f"🔒 Server lockdown started. Locked {len(locked)} channels.")

    @lockdown.command(name="end", description="End server lockdown and unlock affected channels")
    async def lockdown_end(self, interaction: discord.Interaction, message: str = None):
        if not await self.check_command_permissions(interaction, 'lockdown'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)

        locked_ids = self.data.get("locked_channels", set())
        unlocked = 0

        for ch_id in locked_ids.copy():
            ch = interaction.guild.get_channel(ch_id)
            if ch:
                await ch.set_permissions(interaction.guild.default_role, overwrite=discord.PermissionOverwrite(send_messages=True))
                if message:
                    await ch.send(message)
                unlocked += 1

        self.data["locked_channels"] = set()
        self.data["lockdown_active"] = False
        self.data_handler.save_data(self.data)

        await interaction.response.send_message(f"🔓 Lockdown ended. Unlocked {unlocked} channels.")

    @app_commands.command(name="moderations", description="View active moderations for a member")
    @app_commands.describe(
        member="Member to check",
        page="Page number (default 1)"
    )
    async def moderations(self, interaction: discord.Interaction, 
                         member: discord.Member, 
                         page: int = 1):
        """Get a list of active moderations (timed)."""
        if not await self.check_command_permissions(interaction, 'moderations'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
            
        act = [t for t in self.data.get('timed',[]) if t['user_id']==member.id]
        pag = act[(page-1)*5:page*5]
        
        embed = discord.Embed(title=f"Active moderations for {member}", color=discord.Color.green())
        for t in pag:
            embed.add_field(
                name=t['type'].title(),
                value=f"Ends <t:{int(t['end'])}:R>",
                inline=False
            )
            
        if not embed.fields:
            embed.description = "No active moderations"
            
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="modstats", description="View moderation statistics for a member")
    @app_commands.describe(member="Member to view stats for")
    async def modstats(self, interaction: discord.Interaction, member: discord.Member):
        """Get moderation statistics for a mod/admin."""
        if not await self.check_command_permissions(interaction, 'modstats'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
            
        logs = self.data.get('modlogs', {}).get(str(interaction.guild.id), [])
        user_actions = [l for l in logs if l['moderator_id'] == member.id]
        
        if not user_actions:
            return await interaction.response.send_message(f"📊 No moderation actions found for {member.mention}")
            
        action_counts = {}
        for action in user_actions:
            action_type = action['action']
            action_counts[action_type] = action_counts.get(action_type, 0) + 1
            
        embed = discord.Embed(
            title=f"Moderation Stats for {member}",
            color=discord.Color.blurple()
        )
        
        for action, count in sorted(action_counts.items()):
            embed.add_field(name=action, value=str(count), inline=True)
            
        embed.set_footer(text=f"Total actions: {len(user_actions)}")
        await interaction.response.send_message(embed=embed)

    @app_commands.command(name="duration", description="Change duration of a timed moderation")
    @app_commands.describe(
        case_id="Case ID to modify",
        limit="New duration (e.g. 1h, 2d)"
    )
    async def duration(self, interaction: discord.Interaction, 
                      case_id: int, 
                      limit: str):
        """Change the duration of a mute/ban."""
        if not await self.check_command_permissions(interaction, 'duration'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
            
        logs = self.data.get('modlogs', {}).get(str(interaction.guild.id), [])
        for l in logs:
            if l['case_id'] == case_id and l['duration'] is not None:
                try:
                    new_duration = parse_time(limit)
                    l['duration'] = limit
                    
                    # Update timed action
                    for t in self.data.get('timed', []):
                        if t['user_id'] == l['user_id'] and t['type'].lower() == l['action'].lower():
                            t['end'] = datetime.datetime.utcnow().timestamp() + new_duration
                            
                    self.data_handler.save_data(self.data)
                    return await interaction.response.send_message(
                        f"✅ Updated duration for case {case_id} to {limit}"
                    )
                except ValueError:
                    return await interaction.response.send_message(
                        "❌ Invalid duration format. Use like 1h, 30m, 2d",
                        ephemeral=True
                    )
                    
        await interaction.response.send_message("❌ Case not found or not timed.", ephemeral=True)

    @app_commands.command(name="fireboard", description="View fireboard stats for a message")
    @app_commands.describe(link="Message link to check")
    async def fireboard(self, interaction: discord.Interaction, link: str):
        """View fireboard stats for a message."""
        if not await self.check_command_permissions(interaction, 'fireboard'):
            return await interaction.response.send_message("❌ No permission.", ephemeral=True)
            
        # Parse message ID from link
        try:
            # Format: https://discord.com/channels/GUILD_ID/CHANNEL_ID/MESSAGE_ID
            parts = link.split('/')
            message_id = int(parts[-1])
            channel_id = int(parts[-2])
            
            channel = interaction.guild.get_channel(channel_id)
            if not channel:
                return await interaction.response.send_message("❌ Channel not found.", ephemeral=True)
                
            message = await channel.fetch_message(message_id)
            
            # In a real implementation, you would track reactions in your database
            embed = discord.Embed(
                title="Fireboard Stats",
                description=f"Stats for [this message]({link})",
                color=discord.Color.orange()
            )
            embed.add_field(name="🔥 Reactions", value=str(len(message.reactions)))
            embed.add_field(name="💬 Replies", value="Not tracked")  # Would track in database
            
            await interaction.response.send_message(embed=embed)
            
        except (IndexError, ValueError, discord.NotFound, discord.Forbidden):
            await interaction.response.send_message("❌ Invalid message link or unable to fetch message.", ephemeral=True)

    async def log(self, interaction: discord.Interaction, action: str, target, reason: str = None, duration: str = None):
        """Log a moderation action to the modlogs and send an embed to the specified log channel."""
        gid = str(interaction.guild.id)
        logs = self.data.setdefault('modlogs', {}).setdefault(gid, [])
        case_id = len(logs) + 1

        if isinstance(target, discord.Member):
            user_id = target.id
        elif isinstance(target, discord.Object):
            user_id = target.id
        elif isinstance(target, discord.Guild):
            # For server-wide actions like lockdown
            user_id = None
        else:
            try:
                user_id = int(target)
            except (ValueError, TypeError):
                user_id = None

        # Append log data
        logs.append({
            'case_id': case_id,
            'action': action,
            'user_id': user_id,
            'moderator_id': interaction.user.id,
            'reason': reason,
            'duration': duration,
            'timestamp': datetime.datetime.utcnow().isoformat()
        })
        self.data_handler.save_data(self.data)

        # Format the embed
        embed = discord.Embed(
            title=f"Moderation Log: Case #{case_id}",
            description=f"Action: {action}",
            color=discord.Color.blue(),
            timestamp=datetime.datetime.utcnow()
        )

        embed.add_field(name="Moderator", value=interaction.user.mention, inline=False)
        embed.add_field(name="Target", value=f"<@{user_id}>" if user_id else "Server-wide action", inline=False)
        embed.add_field(name="Reason", value=reason or "No reason provided", inline=False)
        embed.add_field(name="Duration", value=duration or "N/A", inline=False)
        embed.add_field(name="Timestamp", value=datetime.datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"), inline=False)

        # Get the log channel from the config
        log_channel_id = self.config.get("mod_log_channel_id")
        if log_channel_id:
            log_channel = interaction.guild.get_channel(log_channel_id)
            if log_channel:
                await log_channel.send(embed=embed)
            else:
                print(f"Log channel with ID {log_channel_id} not found.")
        else:
            print("Log channel ID not found in config.")

        return case_id

def parse_time(time_str: str) -> int:
    """Parse a time string like 1d, 2h, 30m into seconds."""
    if not time_str:
        return 0
        
    units = {
        's': 1,
        'm': 60,
        'h': 60*60,
        'd': 24*60*60,
        'w': 7*24*60*60
    }
    
    try:
        num = int(time_str[:-1])
        unit = time_str[-1].lower()
        if unit not in units:
            raise ValueError
        return num * units[unit]
    except (ValueError, IndexError):
        raise ValueError(f"Invalid time format: {time_str}. Use format like 1h, 30m, 2d")

async def setup(bot):
    await bot.add_cog(Moderation(bot))
