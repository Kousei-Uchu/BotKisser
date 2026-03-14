import discord
from discord.ext import commands, tasks
from discord import app_commands
import asyncio
import datetime
from utils.config_manager import ConfigManager
from utils.db_handlers.sticky_db import StickyDB

# ------------------------
# COG LAYER
# ------------------------
class Sticky(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = ConfigManager('config.json').load_config().get('sticky', {})
        self.db = StickyDB()
        self.sticky_messages = {}       # channel_id -> discord.Message
        self.pending_updates = {}       # channel_id -> asyncio.Task
        self.inactivity_time = self.config.get("inactivity_time", 5)  # seconds

        self.command_configs = {
            'stick': {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_messages']},
            'unstick': {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_messages']},
            'editstick': {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_messages']},
        }

        self.sticky_ready_task.start()

    @tasks.loop(count=1)
    async def sticky_ready_task(self):
        await self.bot.wait_until_ready()
        await self._restore_sticky_messages()

    async def _restore_sticky_messages(self):
        for channel_id, msg_id, content, _ in self.db.all():
            channel = self.bot.get_channel(int(channel_id))
            if not channel:
                continue
            try:
                msg = await channel.fetch_message(int(msg_id))
            except discord.NotFound:
                msg = await channel.send(content)
                self.db.set(channel_id, msg.id, content)
            self.sticky_messages[channel_id] = msg

    async def _debounced_update(self, channel: discord.TextChannel):
        """Wait until channel is inactive, then update sticky message."""
        await asyncio.sleep(self.inactivity_time)
        cid = str(channel.id)
        sticky = self.db.get(cid)
        if not sticky:
            return

        try:
            old_msg = await channel.fetch_message(sticky["message_id"])
            await old_msg.delete()
        except discord.NotFound:
            pass

        new_msg = await channel.send(sticky["content"])
        self.db.set(cid, new_msg.id, sticky["content"])
        self.sticky_messages[cid] = new_msg
        self.pending_updates.pop(cid, None)

    # ------------------------
    # COMMANDS
    # ------------------------
    async def check_command_permissions(self, interaction, name):
        cfg = self.command_configs.get(name, {})
        if not cfg.get('enabled', True):
            return False
        if any(not getattr(interaction.user.guild_permissions, perm, False) for perm in cfg.get('permissions', [])):
            return False
        req_roles = cfg.get('required_roles', [])
        if req_roles and '@everyone' not in req_roles:
            user_roles = {str(r.id) for r in interaction.user.roles}
            if not set(req_roles) & user_roles:
                return False
        return True

    @app_commands.command(name="stick", description="Stick a message to the channel")
    async def stick(self, interaction: discord.Interaction, message: str):
        if not await self.check_command_permissions(interaction, "stick"):
            return await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)

        sent_msg = await interaction.channel.send(message)
        cid = str(interaction.channel.id)
        self.sticky_messages[cid] = sent_msg
        self.db.set(cid, sent_msg.id, message)

        await interaction.response.send_message("📌 Message stuck to channel!", ephemeral=True)
        await interaction.delete_original_response()

    @app_commands.command(name="unstick", description="Remove sticky message from this channel")
    async def unstick(self, interaction: discord.Interaction):
        if not await self.check_command_permissions(interaction, "unstick"):
            return await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)

        cid = str(interaction.channel.id)
        sticky = self.db.get(cid)
        if not sticky:
            return await interaction.response.send_message("ℹ️ No sticky message here.", ephemeral=True)

        try:
            msg = await interaction.channel.fetch_message(sticky["message_id"])
            await msg.delete()
        except discord.NotFound:
            pass

        self.db.remove(cid)
        self.sticky_messages.pop(cid, None)
        task = self.pending_updates.pop(cid, None)
        if task and not task.done():
            task.cancel()

        await interaction.response.send_message("🗑️ Sticky message removed.", ephemeral=True)

    @app_commands.command(name="editstick", description="Edit the sticky message in this channel")
    async def edit_stick(self, interaction: discord.Interaction, new_message: str):
        if not await self.check_command_permissions(interaction, "stick"):
            return await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)

        cid = str(interaction.channel.id)
        sticky = self.db.get(cid)
        if not sticky:
            return await interaction.response.send_message("ℹ️ No sticky message to edit.", ephemeral=True)

        try:
            msg = await interaction.channel.fetch_message(sticky["message_id"])
            await msg.edit(content=new_message)
            self.db.set(cid, msg.id, new_message)
            self.sticky_messages[cid] = msg
            await interaction.response.send_message("✏️ Sticky message updated.", ephemeral=True)
        except discord.NotFound:
            return await interaction.response.send_message("❌ Could not find sticky message to edit.", ephemeral=True)

    # ------------------------
    # MESSAGE HANDLER
    # ------------------------
    @commands.Cog.listener()
    async def on_message(self, message: discord.Message):
        if message.author.bot or not isinstance(message.channel, discord.TextChannel):
            return

        cid = str(message.channel.id)
        if cid in self.sticky_messages and message.id != self.sticky_messages[cid].id:
            # update last activity in DB
            self.db.update_activity(cid)

            # cancel any pending update task
            task = self.pending_updates.get(cid)
            if task and not task.done():
                task.cancel()

            # schedule a new debounced update
            self.pending_updates[cid] = asyncio.create_task(self._debounced_update(message.channel))


async def setup(bot):
    await bot.add_cog(Sticky(bot))