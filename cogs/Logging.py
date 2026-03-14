import discord
from discord.ext import commands
from discord import Embed
from utils.config_manager import ConfigManager
from datetime import datetime, timezone


class Logging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config_manager = ConfigManager('config.json')
        self.config = self.config_manager.load_config()
        self.logging_config = self.config.get('logging', {})

    async def send_log(self, channel_id, title, description, color, event_channel_id=None, footer=None):
        channel = self.bot.get_channel(int(channel_id))
        if channel is None:
            print(f"Error: Channel ID {channel_id} not found!")
            return

        full_description = str(description)
        if event_channel_id is not None and f"<#{event_channel_id}>" not in full_description:
            full_description += f"\n\n**Channel:** <#{event_channel_id}>"

        full_footer = "aawagga"
        if footer:
            full_footer = f"{footer} • aawagga"

        embed = Embed(
            title=title,
            description=full_description,
            color=color
        )
        embed.timestamp = datetime.now(timezone.utc)
        embed.set_footer(text=full_footer)
        await channel.send(embed=embed)

    # Message Delete
    async def message_delete(self, message):
        if message.author.bot:
            return
        channel_id = self.logging_config.get('message_delete_channel')
        if not channel_id:
            return
        embed = Embed(
            title="Message Deleted",
            description=(
                f"**User:** {message.author.mention} ({message.author})\n"
                f"**Message:** {message.content}\n"
                f"**Channel:** <#{message.channel.id}>"
            ),
            color=discord.Color.blue()
        )
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.timestamp = datetime.now(timezone.utc)
        await self.send_log(channel_id, embed.title, embed.description, discord.Color.blue(), message.channel.id)

    # Message Edit
    async def message_edit(self, before, after):
        if before.author.bot:
            return
        channel_id = self.logging_config.get('message_edit_channel')
        if not channel_id:
            return
        embed = Embed(
            title="Message Edited",
            description=(
                f"**User:** {before.author.mention} ({before.author})\n"
                f"**Before:** {before.content}\n"
                f"**After:** {after.content}\n"
                f"**Channel:** <#{before.channel.id}>"
            ),
            color=discord.Color.blue()
        )
        embed.set_author(name=str(before.author), icon_url=before.author.display_avatar.url)
        embed.timestamp = datetime.now(timezone.utc)
        await self.send_log(channel_id, embed.title, embed.description, discord.Color.blue(), before.channel.id)

    # Bulk Message Delete
    async def bulk_message_delete(self, messages):
        if not messages:
            return
        channel_id = self.logging_config.get('bulk_delete_channel')
        if not channel_id:
            return
        displayed_messages = messages[:20]
        description_lines = [f"- {msg.content}" for msg in displayed_messages if msg.content]
        if len(messages) > 20:
            description_lines.append(f"...and {len(messages) - 20} more messages.")
        embed = Embed(
            title="Bulk Message Delete",
            description="**Deleted Messages:**\n" + "\n".join(description_lines),
            color=discord.Color.red()
        )
        event_channel_id = messages[0].channel.id
        embed.timestamp = datetime.now(timezone.utc)
        await self.send_log(channel_id, embed.title, embed.description, discord.Color.red(), event_channel_id)

    # Image Delete
    async def image_message_delete(self, message):
        if not message.attachments:
            return
        channel_id = self.logging_config.get('image_delete_channel')
        if not channel_id:
            return
        embed = Embed(
            title="Image Deleted",
            description=(
                f"**User:** {message.author.mention} ({message.author})\n"
                f"**Image URL:** {message.attachments[0].url}\n"
                f"**Channel:** <#{message.channel.id}>"
            ),
            color=discord.Color.red()
        )
        embed.set_author(name=str(message.author), icon_url=message.author.display_avatar.url)
        embed.timestamp = datetime.now(timezone.utc)
        await self.send_log(channel_id, embed.title, embed.description, discord.Color.red(), message.channel.id)

    # Member Join
    async def on_member_join(self, member):
        channel_id = self.logging_config.get('member_join_channel')
        if not channel_id:
            return
        embed = Embed(
            title="Member Joined",
            description=f"**User:** {member.mention} ({member})",
            color=discord.Color.green()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.timestamp = datetime.now(timezone.utc)
        await self.send_log(channel_id, embed.title, embed.description, discord.Color.green())

    # Member Leave
    async def on_member_remove(self, member):
        channel_id = self.logging_config.get('member_leave_channel')
        if not channel_id:
            return
        roles = ', '.join([f"`{role.name}`" for role in member.roles if role.name != "@everyone"]) or "None"
        embed = Embed(
            title="Member Left",
            description=f"**User:** {member.mention} ({member})\n**Roles:** {roles}",
            color=discord.Color.red()
        )
        embed.set_thumbnail(url=member.display_avatar.url)
        embed.timestamp = datetime.now(timezone.utc)
        await self.send_log(channel_id, embed.title, embed.description, discord.Color.red())

    # Member Role Add / Remove
    async def on_member_update(self, before, after):
        added_roles = [r for r in after.roles if r not in before.roles]
        removed_roles = [r for r in before.roles if r not in after.roles]

        if added_roles:
            channel_id = self.logging_config.get('member_role_add_channel')
            if channel_id:
                embed = Embed(
                    title="Role Added",
                    description=f"**User:** {after.mention} ({after})\n**Added Roles:** {', '.join(f'`{r.name}`' for r in added_roles)}",
                    color=discord.Color.blue()
                )
                embed.set_author(name=str(after), icon_url=after.display_avatar.url)
                embed.timestamp = datetime.now(timezone.utc)
                await self.send_log(channel_id, embed.title, embed.description, discord.Color.blue())

        if removed_roles:
            channel_id = self.logging_config.get('member_role_remove_channel')
            if channel_id:
                embed = Embed(
                    title="Role Removed",
                    description=f"**User:** {after.mention} ({after})\n**Removed Roles:** {', '.join(f'`{r.name}`' for r in removed_roles)}",
                    color=discord.Color.red()
                )
                embed.set_author(name=str(after), icon_url=after.display_avatar.url)
                embed.timestamp = datetime.now(timezone.utc)
                await self.send_log(channel_id, embed.title, embed.description, discord.Color.red())

    # Member Ban / Unban
    async def on_member_ban(self, guild, user):
        channel_id = self.logging_config.get('member_ban_channel')
        if not channel_id:
            return
        embed = Embed(
            title="Member Banned",
            description=f"**User:** {user.mention} ({user})",
            color=discord.Color.red()
        )
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.timestamp = datetime.now(timezone.utc)
        await self.send_log(channel_id, embed.title, embed.description, discord.Color.red())

    async def on_member_unban(self, guild, user):
        channel_id = self.logging_config.get('member_unban_channel')
        if not channel_id:
            return
        embed = Embed(
            title="Member Unbanned",
            description=f"**User:** {user.mention} ({user})",
            color=discord.Color.green()
        )
        embed.set_author(name=str(user), icon_url=user.display_avatar.url)
        embed.timestamp = datetime.now(timezone.utc)
        await self.send_log(channel_id, embed.title, embed.description, discord.Color.green())

    # Role Create / Delete / Update
    async def on_guild_role_create(self, role):
        channel_id = self.logging_config.get('role_create_channel')
        if not channel_id:
            return
        embed = Embed(
            title="Role Created",
            description=f"**Role:** `{role.name}`\n**Role ID:** {role.id}",
            color=discord.Color.blue()
        )
        embed.timestamp = datetime.now(timezone.utc)
        await self.send_log(channel_id, embed.title, embed.description, discord.Color.blue())

    async def on_guild_role_delete(self, role):
        channel_id = self.logging_config.get('role_delete_channel')
        if not channel_id:
            return
        embed = Embed(
            title="Role Deleted",
            description=f"**Role:** `{role.name}`\n**Role ID:** {role.id}",
            color=discord.Color.red()
        )
        embed.timestamp = datetime.now(timezone.utc)
        await self.send_log(channel_id, embed.title, embed.description, discord.Color.red())

    async def on_guild_role_update(self, before, after):
        channel_id = self.logging_config.get('role_update_channel')
        if not channel_id:
            return

        changes = []

        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` → `{after.name}`")
        if before.color != after.color:
            changes.append(f"**Color:** `{before.color}` → `{after.color}`")
        if before.mentionable != after.mentionable:
            changes.append(f"**Mentionable:** `{before.mentionable}` → `{after.mentionable}`")
        if before.hoist != after.hoist:
            changes.append(f"**Displayed Separately (hoist):** `{before.hoist}` → `{after.hoist}`")
        if before.position != after.position:
            changes.append(f"**Position:** `{before.position}` → `{after.position}`")

        # Permissions diff
        added = [p[0] for p in after.permissions if getattr(before.permissions, p[0]) != getattr(after.permissions, p[0]) and getattr(after.permissions, p[0])]
        removed = [p[0] for p in after.permissions if getattr(before.permissions, p[0]) != getattr(after.permissions, p[0]) and not getattr(after.permissions, p[0])]
        if added:
            changes.append(f"**Permissions Added:** {', '.join(f'`{p}`' for p in added)}")
        if removed:
            changes.append(f"**Permissions Removed:** {', '.join(f'`{p}`' for p in removed)}")

        if not changes:
            return

        embed = Embed(
            title="Role Updated",
            description=f"**Role:** `{before.name}` (`{before.id}`)\n\n" + "\n".join(changes),
            color=discord.Color.blue()
        )
        embed.timestamp = datetime.now(timezone.utc)
        await self.send_log(channel_id, embed.title, embed.description, discord.Color.blue())

    # Channel Create / Delete / Update
    async def on_guild_channel_create(self, channel):
        channel_id = self.logging_config.get('channel_create_channel')
        if not channel_id:
            return
        embed = Embed(
            title="Channel Created",
            description=f"**Channel:** <#{channel.id}>",
            color=discord.Color.blue()
        )
        embed.timestamp = datetime.now(timezone.utc)
        await self.send_log(channel_id, embed.title, embed.description, discord.Color.blue())

    async def on_guild_channel_delete(self, channel):
        channel_id = self.logging_config.get('channel_delete_channel')
        if not channel_id:
            return
        embed = Embed(
            title="Channel Deleted",
            description=f"**Channel:** <#{channel.id}>\n**Name:** `{channel.name}`\n**Type:** `{channel.type}`",
            color=discord.Color.red()
        )
        embed.timestamp = datetime.now(timezone.utc)
        await self.send_log(channel_id, embed.title, embed.description, discord.Color.red())

    async def on_guild_channel_update(self, before, after):
        channel_id = self.logging_config.get('channel_update_channel')
        if not channel_id:
            return
        changes = []

        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` → `{after.name}`")
        if hasattr(before, 'topic') and before.topic != getattr(after, 'topic', None):
            changes.append(f"**Topic:** `{before.topic or 'None'}` → `{after.topic or 'None'}`")
        if hasattr(before, 'nsfw') and before.nsfw != getattr(after, 'nsfw', None):
            changes.append(f"**NSFW:** `{before.nsfw}` → `{after.nsfw}`")
        if hasattr(before, 'bitrate') and before.bitrate != getattr(after, 'bitrate', None):
            changes.append(f"**Bitrate:** `{before.bitrate}` → `{after.bitrate}`")
        if hasattr(before, 'user_limit') and before.user_limit != getattr(after, 'user_limit', None):
            changes.append(f"**User Limit:** `{before.user_limit}` → `{after.user_limit}`")
        before_parent = f"<#{before.category.id}>" if before.category else "None"
        after_parent = f"<#{after.category.id}>" if after.category else "None"
        if before.category != after.category:
            changes.append(f"**Category:** {before_parent} → {after_parent}")
        if hasattr(before, 'slowmode_delay') and before.slowmode_delay != getattr(after, 'slowmode_delay', None):
            changes.append(f"**Slowmode Delay:** `{before.slowmode_delay}` → `{after.slowmode_delay}` seconds")
        if before.type != after.type:
            changes.append(f"**Channel Type:** `{before.type}` → `{after.type}`")
        if before.position != after.position:
            changes.append(f"**Position:** `{before.position}` → `{after.position}`")

        # Permission overwrites
        def perm_diff(old, new):
            added = []
            removed = []
            changed = []

            perms = [
                'add_reactions', 'administrator', 'attach_files', 'ban_members', 'change_nickname',
                'connect', 'create_instant_invite', 'deafen_members', 'embed_links', 'kick_members',
                'manage_channels', 'manage_emojis', 'manage_guild', 'manage_messages', 'manage_nicknames',
                'manage_roles', 'manage_webhooks', 'mention_everyone', 'move_members', 'mute_members',
                'priority_speaker', 'read_message_history', 'read_messages', 'send_messages',
                'send_tts_messages', 'speak', 'use_external_emojis', 'use_slash_commands',
                'view_audit_log', 'view_channel',
            ]

            for perm in perms:
                old_val = getattr(old, perm)
                new_val = getattr(new, perm)
                if old_val != new_val:
                    if old_val is None:
                        added.append(f"{perm}={new_val}")
                    elif new_val is None:
                        removed.append(f"{perm}={old_val}")
                    else:
                        changed.append(f"{perm}: `{old_val}` → `{new_val}`")
            result = []
            if added:
                result.append("Added: " + ", ".join(added))
            if removed:
                result.append("Removed: " + ", ".join(removed))
            if changed:
                result.append("Changed: " + ", ".join(changed))
            return result

        before_overwrites = {t.id: o for t, o in before.overwrites.items()}
        after_overwrites = {t.id: o for t, o in after.overwrites.items()}
        all_targets = set(before_overwrites.keys()) | set(after_overwrites.keys())
        for tid in all_targets:
            b = before_overwrites.get(tid)
            a = after_overwrites.get(tid)
            target_name = None
            if before.guild:
                role = before.guild.get_role(tid)
                member = before.guild.get_member(tid)
                if role:
                    target_name = f"`@{role.name}`"
                elif member:
                    target_name = member.mention
                else:
                    target_name = f"ID {tid}"
            else:
                target_name = f"ID {tid}"

            if b and a:
                diffs = perm_diff(b, a)
                if diffs:
                    changes.append(f"**Permission Overwrites Changed for {target_name}:** " + "; ".join(diffs))
            elif b and not a:
                changes.append(f"**Permission Overwrites Removed for {target_name}**")
            elif a and not b:
                changes.append(f"**Permission Overwrites Added for {target_name}**")

        if not changes:
            return

        embed = Embed(
            title="Channel Updated",
            description=f"**Channel:** <#{before.id}>\n\n" + "\n".join(changes),
            color=discord.Color.orange()
        )
        embed.timestamp = datetime.now(timezone.utc)
        await self.send_log(channel_id, embed.title, embed.description, discord.Color.orange())

async def setup(bot: commands.Bot):
    await bot.add_cog(Logging(bot))