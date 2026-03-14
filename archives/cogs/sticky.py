import discord
from discord.ext import commands, tasks
from discord import app_commands
from utils.data_handler import DataHandler
from utils.config_manager import ConfigManager

class Sticky(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.data_handler = DataHandler('data/sticky.json')
        self.config = ConfigManager('config.json').load_config().get('sticky', {})
        self.sticky_messages = {}

        self.command_configs = {
            'stick': {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_messages']},
            'unstick': {'enabled': True, 'required_roles': ['@everyone'], 'permissions': ['manage_messages']},
        }
        self._merge_config_commands()
        self.sticky_ready_task.start()

    def _merge_config_commands(self):
        for name, cfg in self.config.get('commands', {}).items():
            if name in self.command_configs:
                self.command_configs[name].update(cfg)

    async def check_command_permissions(self, interaction: discord.Interaction, name: str) -> bool:
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

    @tasks.loop(count=1)
    async def sticky_ready_task(self):
        await self.bot.wait_until_ready()
        await self._restore_sticky_messages()

    async def _restore_sticky_messages(self):
        data = self.data_handler.load_data()
        for channel_id, info in data.items():
            channel = self.bot.get_channel(int(channel_id))
            if not channel:
                continue
            try:
                msg = await channel.fetch_message(info['message_id'])
            except discord.NotFound:
                msg = await channel.send(info['content'])
                info['message_id'] = msg.id
                self.data_handler.save_data(data)
            self.sticky_messages[channel_id] = msg

    @app_commands.command(name="stick", description="Stick a message to the channel")
    async def stick(self, interaction: discord.Interaction, message: str):
        if not await self.check_command_permissions(interaction, 'stick'):
            return await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)

        sent_msg = await interaction.channel.send(message)
        cid = str(interaction.channel.id)
        self.sticky_messages[cid] = sent_msg
        self.data_handler.save_data({**self.data_handler.load_data(), cid: {'message_id': sent_msg.id, 'content': message}})

        await interaction.response.send_message("📌 Message stuck to channel!", ephemeral=True)
        await interaction.delete_original_response()

    @app_commands.command(name="unstick", description="Remove the sticky message from this channel")
    async def unstick(self, interaction: discord.Interaction):
        if not await self.check_command_permissions(interaction, 'unstick'):
            return await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)

        cid = str(interaction.channel.id)
        data = self.data_handler.load_data()

        if cid not in data:
            return await interaction.response.send_message("ℹ️ No sticky message here.", ephemeral=True)

        try:
            msg = await interaction.channel.fetch_message(data[cid]['message_id'])
            await msg.delete()
        except discord.NotFound:
            pass

        data.pop(cid)
        self.data_handler.save_data(data)
        self.sticky_messages.pop(cid, None)

        await interaction.response.send_message("🗑️ Sticky message removed.", ephemeral=True)

    @app_commands.command(name="editstick", description="Edit the sticky message in this channel")
    async def edit_stick(self, interaction: discord.Interaction, new_message: str):
        if not await self.check_command_permissions(interaction, 'stick'):
            return await interaction.response.send_message("❌ You don't have permission!", ephemeral=True)

        cid = str(interaction.channel.id)
        data = self.data_handler.load_data()

        if cid not in data:
            return await interaction.response.send_message("ℹ️ No sticky message to edit.", ephemeral=True)

        try:
            msg = await interaction.channel.fetch_message(data[cid]['message_id'])
            await msg.edit(content=new_message)
            data[cid]['content'] = new_message
            self.data_handler.save_data(data)
            self.sticky_messages[cid] = msg
            await interaction.response.send_message("✏️ Sticky message updated.", ephemeral=True)
        except discord.NotFound:
            return await interaction.response.send_message("❌ Could not find the sticky message to edit.", ephemeral=True)

    async def update_sticky_message(self, channel: discord.TextChannel):
        cid = str(channel.id)
        data = self.data_handler.load_data()
        if cid not in data:
            return

        try:
            old = await channel.fetch_message(data[cid]['message_id'])
            await old.delete()
        except discord.NotFound:
            pass

        new_msg = await channel.send(data[cid]['content'])
        data[cid]['message_id'] = new_msg.id
        self.sticky_messages[cid] = new_msg
        self.data_handler.save_data(data)

    async def on_message(self, message: discord.Message):
        if message.author.bot or not isinstance(message.channel, discord.TextChannel):
            return

        cid = str(message.channel.id)
        if cid in self.sticky_messages and message.id != self.sticky_messages[cid].id:
            await self.update_sticky_message(message.channel)

    @commands.Cog.listener()
    async def on_command_error(self, ctx, error):
        if isinstance(error, (commands.CommandNotFound, commands.MissingPermissions)):
            return await ctx.send("❌ You don't have permission!", ephemeral=True)
        await ctx.send(f"⚠️ Error: {error}", ephemeral=True)

async def setup(bot):
    await bot.add_cog(Sticky(bot))
