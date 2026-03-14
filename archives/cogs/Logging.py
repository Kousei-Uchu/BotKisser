import discord
from discord.ext import commands
from discord import Embed
from utils.config_manager import ConfigManager
from datetime import datetime, timezone


class Logging(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config_manager = ConfigManager('config.json')
        self.config = self.config_manager.load_config()  # Load the full config
        self.logging_config = self.config.get('logging', {})  # Get only the logging section

    async def send_log(self, channel_id, title, description, color, event_channel_id=None, footer=None):
        """Send log embed to specified channel."""
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
        if channel_id:
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
        if channel_id:
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
        if channel_id:
            # Limit to first 20 messages to avoid huge embeds
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
        if message.attachments:
            channel_id = self.logging_config.get('image_delete_channel')
            if channel_id:
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
        if channel_id:
            embed = Embed(
                title="Member Joined",
                description=(
                    f"**User:** {member.mention} ({member})\n"
                ),
                color=discord.Color.green()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.timestamp = datetime.now(timezone.utc)

            await self.send_log(channel_id, embed.title, embed.description, discord.Color.green())

    # Member Leave
    async def on_member_remove(self, member):
        channel_id = self.logging_config.get('member_leave_channel')
        if channel_id:
            roles = ', '.join([f"`{role.name}`" for role in member.roles if role.name != "@everyone"]) or "None"
            embed = Embed(
                title="Member Left",
                description=(
                    f"**User:** {member.mention} ({member})\n"
                    f"**Roles:** {roles}\n"
                ),
                color=discord.Color.red()
            )
            embed.set_thumbnail(url=member.display_avatar.url)
            embed.timestamp = datetime.now(timezone.utc)

            await self.send_log(channel_id, embed.title, embed.description, discord.Color.red())

    # Member Role Add / Remove
    async def on_member_update(self, before, after):
        if before.roles != after.roles:
            added_roles = [f"`{role.name}`" for role in after.roles if role not in before.roles]
            removed_roles = [f"`{role.name}`" for role in before.roles if role not in after.roles]

            if added_roles:
                channel_id = self.logging_config.get('member_role_add_channel')
                if channel_id:
                    embed = Embed(
                        title="Role Added",
                        description=(
                            f"**User:** {after.mention} ({after})\n"
                            f"**Added Roles:** {', '.join(added_roles)}"
                        ),
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
                        description=(
                            f"**User:** {after.mention} ({after})\n"
                            f"**Removed Roles:** {', '.join(removed_roles)}"
                        ),
                        color=discord.Color.red()
                    )
                    embed.set_author(name=str(after), icon_url=after.display_avatar.url)
                    embed.timestamp = datetime.now(timezone.utc)

                    await self.send_log(channel_id, embed.title, embed.description, discord.Color.red())

    # Member Ban
    async def on_member_ban(self, guild, user):
        channel_id = self.logging_config.get('member_ban_channel')
        if channel_id:
            embed = Embed(
                title="Member Banned",
                description=f"**User:** {user.mention} ({user})",
                color=discord.Color.red()
            )
            embed.set_author(name=str(user), icon_url=user.display_avatar.url)
            embed.timestamp = datetime.now(timezone.utc)

            await self.send_log(channel_id, embed.title, embed.description, discord.Color.red())

    # Member Unban
    async def on_member_unban(self, guild, user):
        channel_id = self.logging_config.get('member_unban_channel')
        if channel_id:
            embed = Embed(
                title="Member Unbanned",
                description=f"**User:** {user.mention} ({user})",
                color=discord.Color.green()
            )
            embed.set_author(name=str(user), icon_url=user.display_avatar.url)
            embed.timestamp = datetime.now(timezone.utc)

            await self.send_log(channel_id, embed.title, embed.description, discord.Color.green())

    # Role Create
    async def on_guild_role_create(self, role):
        channel_id = self.logging_config.get('role_create_channel')
        if channel_id:
            embed = Embed(
                title="Role Created",
                description=f"**Role:** `{role.name}`\n**Role ID:** {role.id}",
                color=discord.Color.blue()
            )
            embed.timestamp = datetime.now(timezone.utc)

            await self.send_log(channel_id, embed.title, embed.description, discord.Color.blue())

    # Role Delete
    async def on_guild_role_delete(self, role):
        channel_id = self.logging_config.get('role_delete_channel')
        if channel_id:
            embed = Embed(
                title="Role Deleted",
                description=f"**Role:** `{role.name}`\n**Role ID:** {role.id}",
                color=discord.Color.red()
            )
            embed.timestamp = datetime.now(timezone.utc)

            await self.send_log(channel_id, embed.title, embed.description, discord.Color.red())

    # Role Update
    async def on_guild_role_update(self, before, after):
        channel_id = self.logging_config.get('role_update_channel')
        if not channel_id:
            return

        changes = []

        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` → `{after.name}`")

        if before.color != after.color:
            changes.append(f"**Color:** `{before.color}` → `{after.color}`")

        if before.permissions != after.permissions:
            added = []
            removed = []
            for perm, value in after.permissions:
                before_value = getattr(before.permissions, perm)
                if value != before_value:
                    if value:
                        added.append(perm)
                    else:
                        removed.append(perm)

            if added:
                changes.append(f"**Permissions Added:** {', '.join(f'`{p}`' for p in added)}")
            if removed:
                changes.append(f"**Permissions Removed:** {', '.join(f'`{p}`' for p in removed)}")

        if before.mentionable != after.mentionable:
            changes.append(f"**Mentionable:** `{before.mentionable}` → `{after.mentionable}`")

        if before.hoist != after.hoist:
            changes.append(f"**Displayed Separately (hoist):** `{before.hoist}` → `{after.hoist}`")

        if before.position != after.position:
            changes.append(f"**Position:** `{before.position}` → `{after.position}`")

        if not changes:
            return

        embed = Embed(
            title="Role Updated",
            description=f"**Role:** `{before.name}` (`{before.id}`)\n\n" + "\n".join(changes),
            color=discord.Color.blue()
        )
        embed.timestamp = datetime.now(timezone.utc)

        await self.send_log(channel_id, embed.title, embed.description, discord.Color.blue())

    # Channel Create
    async def on_guild_channel_create(self, channel):
        channel_id = self.logging_config.get('channel_create_channel')
        if channel_id:
            embed = Embed(
                title="Channel Created",
                description=f"**Channel:** <#{channel.id}>",
                color=discord.Color.blue()
            )
            embed.timestamp = datetime.now(timezone.utc)

            await self.send_log(channel_id, embed.title, embed.description, discord.Color.blue())

    # Channel Delete
    async def on_guild_channel_delete(self, channel):
        channel_id = self.logging_config.get('channel_delete_channel')
        if channel_id:
            embed = Embed(
                title="Channel Deleted",
                description=f"**Channel:** <#{channel.id}>",
                color=discord.Color.red()
            )
            embed.timestamp = datetime.now(timezone.utc)

            await self.send_log(channel_id, embed.title, embed.description, discord.Color.red())

    # Emoji Create
    async def on_guild_emoji_create(self, emoji):
        channel_id = self.logging_config.get('emoji_create_channel')
        if channel_id:
            embed = Embed(
                title="Emoji Created",
                description=f"**Emoji:** `{emoji}` (ID: {emoji.id})",
                color=discord.Color.blue()
            )
            embed.timestamp = datetime.now(timezone.utc)

            await self.send_log(channel_id, embed.title, embed.description, discord.Color.blue(), footer=f"Created at {int(datetime.now(timezone.utc).timestamp())}")

    # Emoji Delete
    async def on_guild_emoji_delete(self, emoji):
        channel_id = self.logging_config.get('emoji_delete_channel')
        if channel_id:
            embed = Embed(
                title="Emoji Deleted",
                description=f"**Emoji:** `{emoji}` (ID: {emoji.id})",
                color=discord.Color.red()
            )
            embed.timestamp = datetime.now(timezone.utc)

            await self.send_log(channel_id, embed.title, embed.description, discord.Color.red())

    # Emoji Update
    async def on_guild_emoji_update(self, before, after):
        channel_id = self.logging_config.get('emoji_update_channel')
        if channel_id:
            embed = Embed(
                title="Emoji Updated",
                description=f"**Before:** `{before}` (ID: {before.id})\n**After:** `{after}` (ID: {after.id})",
                color=discord.Color.orange()
            )
            embed.timestamp = datetime.now(timezone.utc)

            await self.send_log(channel_id, embed.title, embed.description, discord.Color.orange())

    # Voice Channel Join/Leave
    async def on_voice_state_update(self, member, before, after):
        if before.channel != after.channel:
            if after.channel:
                channel_id = self.logging_config.get('voice_join_channel')
                if channel_id:
                    embed = Embed(
                        title="Voice Channel Join",
                        description=(
                            f"**User:** {member.mention} ({member})\n"
                            f"**Channel:** <#{after.channel.id}>"
                        ),
                        color=discord.Color.green()
                    )
                    embed.set_author(name=str(member), icon_url=member.display_avatar.url)
                    embed.timestamp = datetime.now(timezone.utc)

                    await self.send_log(channel_id, embed.title, embed.description, discord.Color.green())
            if before.channel:
                channel_id = self.logging_config.get('voice_leave_channel')
                if channel_id:
                    embed = Embed(
                        title="Voice Channel Leave",
                        description=(
                            f"**User:** {member.mention} ({member})\n"
                            f"**Channel:** <#{before.channel.id}>"
                        ),
                        color=discord.Color.red()
                    )
                    embed.set_author(name=str(member), icon_url=member.display_avatar.url)
                    embed.timestamp = datetime.now(timezone.utc)

                    await self.send_log(channel_id, embed.title, embed.description, discord.Color.red())

    # Channel Update
    async def on_guild_channel_update(self, before, after):
        channel_id = self.logging_config.get('channel_update_channel')
        if not channel_id:
            return

        changes = []

        if before.name != after.name:
            changes.append(f"**Name:** `{before.name}` → `{after.name}`")

        if hasattr(before, 'topic') and before.topic != getattr(after, 'topic', None):
            before_topic = before.topic or "None"
            after_topic = after.topic or "None"
            changes.append(f"**Topic:** `{before_topic}` → `{after_topic}`")

        if hasattr(before, 'nsfw') and before.nsfw != getattr(after, 'nsfw', None):
            changes.append(f"**NSFW:** `{before.nsfw}` → `{after.nsfw}`")

        if hasattr(before, 'bitrate') and before.bitrate != getattr(after, 'bitrate', None):
            changes.append(f"**Bitrate:** `{before.bitrate}` → `{after.bitrate}`")

        if hasattr(before, 'user_limit') and before.user_limit != getattr(after, 'user_limit', None):
            changes.append(f"**User Limit:** `{before.user_limit}` → `{after.user_limit}`")

        before_parent_mention = f"<#{before.category.id}>" if before.category else "None"
        after_parent_mention = f"<#{after.category.id}>" if after.category else "None"
        if before.category != after.category:
            changes.append(f"**Category:** {before_parent_mention} → {after_parent_mention}")

        if hasattr(before, 'slowmode_delay') and before.slowmode_delay != getattr(after, 'slowmode_delay', None):
            changes.append(f"**Slowmode Delay:** `{before.slowmode_delay}` → `{after.slowmode_delay}` seconds")

        if before.type != after.type:
            changes.append(f"**Channel Type:** `{before.type}` → `{after.type}`")

        if before.position != after.position:
            changes.append(f"**Position:** `{before.position}` → `{after.position}`")

        def perm_diff(old: discord.PermissionOverwrite, new: discord.PermissionOverwrite):
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

            return added, removed, changed

        before_overwrites = {target.id: target for target in before.overwrites}
        after_overwrites = {target.id: target for target in after.overwrites}
        all_targets = set(before_overwrites.keys()) | set(after_overwrites.keys())

        for target_id in all_targets:
            before_ow = before_overwrites.get(target_id)
            after_ow = after_overwrites.get(target_id)

            target_name = None
            if before.guild:
                target_role = before.guild.get_role(target_id)
                if target_role:
                    target_name = f"`@{target_role.name}`"
                else:
                    member = before.guild.get_member(target_id)
                    target_name = member.mention if member else f"ID {target_id}"
            else:
                target_name = f"ID {target_id}"

            if before_ow and not after_ow:
                changes.append(f"**Permission Overwrites Removed for {target_name}:**")
            elif not before_ow and after_ow:
                changes.append(f"**Permission Overwrites Added for {target_name}:**")
            else:
                added, removed, changed_perms = perm_diff(before_ow, after_ow)
                if added or removed or changed_perms:
                    changes.append(f"**Permission Overwrites Changed for {target_name}:**")
                    if added:
                        changes.append(f"Added: {', '.join(added)}")
                    if removed:
                        changes.append(f"Removed: {', '.join(removed)}")
                    if changed_perms:
                        changes.append(f"Changed: {', '.join(changed_perms)}")

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