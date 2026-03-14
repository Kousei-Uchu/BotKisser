import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button, Select
import datetime
from utils.data_handler import DataHandler
from utils.config_manager import ConfigManager

TICKET_OPEN_CID = "ticket:open_ticket"
TICKET_CLOSE_PREFIX = "ticket:close_"
TICKET_ADD_PREFIX = "ticket:add_member_"
TICKET_REM_PREFIX = "ticket:remove_member_"

class MemberSelect(Select):
    def __init__(self, members, callback_fn, placeholder):
        self.callback_fn = callback_fn
        options = [
            discord.SelectOption(label=m.display_name, value=str(m.id))
            for m in members if not m.bot
        ][:25]
        super().__init__(placeholder=placeholder, min_values=1, max_values=1, options=options)

    async def callback(self, interaction: discord.Interaction):
        await self.callback_fn(interaction, int(self.values[0]))

class MemberSelectView(View):
    def __init__(self, members, callback_fn, placeholder):
        super().__init__(timeout=60)
        self.add_item(MemberSelect(members, callback_fn, placeholder))

class OpenTicketView(View):
    def __init__(self, cog: "Ticket"):
        super().__init__(timeout=None)
        self.cog = cog
        btn = Button(
            label=self.cog.config.get("panel_button_label", "🎫 Open Ticket"),
            style=discord.ButtonStyle.blurple,
            custom_id=TICKET_OPEN_CID
        )
        btn.callback = self.open_cb
        self.add_item(btn)

    async def open_cb(self, interaction: discord.Interaction):
        await self.cog._create_ticket(interaction)

class ManagementView(View):
    def __init__(self, cog: "Ticket", channel_id: int):
        super().__init__(timeout=None)
        self.cog = cog
        self.channel_id = channel_id

        btn_close = Button(label="Close Ticket", style=discord.ButtonStyle.red, custom_id=f"{TICKET_CLOSE_PREFIX}{channel_id}")
        btn_close.callback = self.close_cb
        self.add_item(btn_close)

        btn_add = Button(label="Add Member", style=discord.ButtonStyle.green, custom_id=f"{TICKET_ADD_PREFIX}{channel_id}")
        btn_add.callback = self.add_cb
        self.add_item(btn_add)

        btn_rem = Button(label="Remove Member", style=discord.ButtonStyle.grey, custom_id=f"{TICKET_REM_PREFIX}{channel_id}")
        btn_rem.callback = self.rem_cb
        self.add_item(btn_rem)

    async def close_cb(self, interaction: discord.Interaction):
        channel = self.cog.bot.get_channel(self.channel_id)
        await self.cog.close_ticket_cmd(interaction, channel)

    async def add_cb(self, interaction: discord.Interaction):
        channel = self.cog.bot.get_channel(self.channel_id)
        await self.cog.add_member(interaction, channel)

    async def rem_cb(self, interaction: discord.Interaction):
        channel = self.cog.bot.get_channel(self.channel_id)
        await self.cog.remove_member(interaction, channel)

class Ticket(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.data_handler = DataHandler('data/tickets.json')
        self.config_manager = ConfigManager('config.json')
        self.config = self.config_manager.load_config().get('ticket', {})
        self.store = self.data_handler.load_data()

        for gid in list(self.store):
            self.store.setdefault(gid, {}).setdefault('open_tickets', {})
            self.store[gid].setdefault('transcripts', {})

        self.command_configs = {
            'ticket':        {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'ticket_button': {'enabled': True, 'required_roles': ['@everyone'], 'permissions': []},
            'addmember':     {'enabled': True, 'required_roles': self.config.get('staff_roles', []), 'permissions': []},
            'removemember':  {'enabled': True, 'required_roles': self.config.get('staff_roles', []), 'permissions': []},
            'close_ticket':  {'enabled': True, 'required_roles': self.config.get('staff_roles', []), 'permissions': []},
        }

        for name, cfg in self.config.get('commands', {}).items():
            if name in self.command_configs:
                self.command_configs[name].update(cfg)

        bot.add_view(OpenTicketView(self))

        for gid, guild_data in self.store.items():
            for cid_str in guild_data.get('open_tickets', {}):
                if cid_str.isdigit():
                    bot.add_view(ManagementView(self, int(cid_str)))

    def _save(self):
        self.data_handler.save_data(self.store)

    async def check_perms(self, interaction: discord.Interaction, name: str):
        cfg = self.command_configs.get(name, {})
        if not cfg.get('enabled', True): return False
        req = cfg.get('required_roles', [])
        if req and '@everyone' not in req:
            user_roles = {str(r.id) for r in interaction.user.roles}
            if not user_roles.intersection(set(req)): return False
        for p in cfg.get('permissions', []):
            if not getattr(interaction.user.guild_permissions, p, False): return False
        return True

    async def _create_ticket(self, interaction: discord.Interaction):
        if not await self.check_perms(interaction, 'ticket_button'):
            return await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        
        gid = str(interaction.guild.id)
        uid = str(interaction.user.id)
        data = self.store.setdefault(gid, {'open_tickets': {}, 'transcripts': {}})
        is_staff = any(str(r.id) in self.config.get('staff_roles', []) for r in interaction.user.roles)

        if not is_staff:
            for tinfo in data['open_tickets'].values():
                if tinfo['user_id'] == uid:
                    return await interaction.response.send_message(self.config.get('already_open_message', "You already have an open ticket."), ephemeral=True)

        cat = discord.utils.get(interaction.guild.categories, id=self.config.get('category_id'))
        if not cat:
            return await interaction.response.send_message("❌ Ticket category not configured.", ephemeral=True)

        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.display_name}",
            category=cat,
            reason=f"Ticket opened by {interaction.user}"
        )
        await channel.set_permissions(interaction.guild.default_role, read_messages=False)
        await channel.set_permissions(interaction.user, read_messages=True, send_messages=True)
        for rid in self.config.get('staff_roles', []):
            role = interaction.guild.get_role(rid)
            if role:
                await channel.set_permissions(role, read_messages=True, send_messages=True)

        data['open_tickets'][str(channel.id)] = {
            'user_id': uid,
            'created_at': datetime.datetime.utcnow().isoformat(),
            'members': [uid]
        }
        self._save()

        embed = discord.Embed(
            title=self.config.get('ticket_embed_title', "Support Ticket"),
            description=self.config.get('ticket_embed_desc', "Please describe your issue."),
            color=discord.Color.blue()
        )
        view = ManagementView(self, channel.id)
        await channel.send(embed=embed, view=view)
        self.bot.add_view(view)

        return await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)

    @app_commands.command(name="ticket", description="Create a new support ticket.")
    async def ticket_cmd(self, interaction: discord.Interaction):
        if not await self.check_perms(interaction, 'ticket'):
            return await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        await self._create_ticket(interaction)

    @app_commands.command(name="ticket_button", description="Post the ticket panel embed.")
    async def ticket_button_cmd(self, interaction: discord.Interaction):
        if not await self.check_perms(interaction, 'ticket_button'):
            return await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)

        panel_ch = interaction.guild.get_channel(self.config.get('panel_channel_id'))
        if not panel_ch:
            return await interaction.response.send_message("❌ Panel channel not found.", ephemeral=True)

        embed = discord.Embed(
            title=self.config.get('panel_embed_title', "Open a Ticket"),
            description=self.config.get('panel_embed_description', "Click below to open a ticket."),
            color=discord.Color.green()
        )
        view = OpenTicketView(self)
        await panel_ch.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Panel posted in {panel_ch.mention}", ephemeral=True)

    async def close_ticket_cmd(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await self.check_perms(interaction, 'close_ticket'):
            return await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)

        messages = [msg async for msg in channel.history(limit=1000, oldest_first=True)]
        embeds = []
        for chunk in [messages[i:i + 10] for i in range(0, len(messages), 10)]:
            embed = discord.Embed(title=f"Transcript for #{channel.name}", color=discord.Color.purple())
            for msg in chunk:
                content = msg.content or "[No content]"
                if msg.attachments:
                    content += "\n" + "\n".join(f"📎 {a.url}" for a in msg.attachments)
                name = f"{msg.author.display_name} • {msg.created_at.strftime('%Y-%m-%d %H:%M:%S UTC')}"
                embed.add_field(name=name, value=content[:1024], inline=False)
            embeds.append(embed)

        log_channel_id = self.config.get("transcript_log_channel_id")
        if log_channel_id:
            log_channel = channel.guild.get_channel(log_channel_id)
            if log_channel:
                for e in embeds:
                    await log_channel.send(embed=e)

        gid = str(channel.guild.id)
        cid = str(channel.id)
        await channel.delete(reason="Ticket closed")
        self.store[gid]['open_tickets'].pop(cid, None)
        self._save()

    async def add_member(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await self.check_perms(interaction, 'addmember'):
            return await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)
        
        members = [m for m in interaction.guild.members if m not in channel.members and not m.bot]
        await interaction.response.send_message("Select a member to add:", view=MemberSelectView(members, lambda i, mid: self._add_selected_member(i, channel, mid), "Select member to add"), ephemeral=True)

    async def _add_selected_member(self, interaction: discord.Interaction, channel, member_id: int):
        m = interaction.guild.get_member(member_id)
        await channel.set_permissions(m, read_messages=True, send_messages=True)
        gid = str(channel.guild.id)
        tid = str(channel.id)
        tinfo = self.store[gid]['open_tickets'][tid]
        if str(m.id) not in tinfo['members']:
            tinfo['members'].append(str(m.id))
            self._save()
        await interaction.response.send_message(f"✅ Added {m.mention}", ephemeral=True)

    async def remove_member(self, interaction: discord.Interaction, channel: discord.TextChannel):
        if not await self.check_perms(interaction, 'removemember'):
            return await interaction.response.send_message("❌ You don't have permission.", ephemeral=True)

        members = [m for m in channel.members if m != interaction.guild.me and not m.bot]
        await interaction.response.send_message("Select a member to remove:", view=MemberSelectView(members, lambda i, mid: self._remove_selected_member(i, channel, mid), "Select member to remove"), ephemeral=True)

    async def _remove_selected_member(self, interaction: discord.Interaction, channel, member_id: int):
        m = interaction.guild.get_member(member_id)
        await channel.set_permissions(m, overwrite=None)
        gid = str(channel.guild.id)
        tid = str(channel.id)
        tinfo = self.store[gid]['open_tickets'][tid]
        if str(m.id) in tinfo['members']:
            tinfo['members'].remove(str(m.id))
            self._save()
        await interaction.response.send_message(f"✅ Removed {m.mention}", ephemeral=True)

async def setup(bot: commands.Bot):
    await bot.add_cog(Ticket(bot))
