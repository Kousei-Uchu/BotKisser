import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
import asyncio
from utils.config_manager import ConfigManager
from utils.db_handlers.ticket_db import TicketDB

TICKET_OPEN_CID   = "ticket:open_ticket"
TICKET_CLOSE_PREFIX  = "ticket:close_"
TICKET_ADD_PREFIX    = "ticket:add_member_"
TICKET_REM_PREFIX    = "ticket:remove_member_"

# ------------------------
# BUTTONS & VIEWS
# ------------------------

class CloseConfirmButton(Button):
    def __init__(self, cog, ticket_id: int, opener_id: int):
        super().__init__(label="Confirm Close", style=discord.ButtonStyle.red)
        self.cog       = cog
        self.ticket_id = ticket_id
        self.opener_id = opener_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.opener_id:
            return await interaction.response.send_message("Only the ticket opener can confirm closing.", ephemeral=True)

        ticket = self.cog.db.get_ticket_by_id(self.ticket_id)
        if not ticket:
            return await interaction.response.send_message("Ticket not found or already closed.", ephemeral=True)

        await interaction.channel.delete(reason=f"Ticket closed by {interaction.user}")
        self.cog.db.close_ticket(self.ticket_id)
        await interaction.response.send_message("Ticket closed successfully.", ephemeral=True)


class OpenTicketView(View):
    def __init__(self, cog):
        super().__init__(timeout=None)
        self.cog = cog
        btn = Button(
            label=cog.config.get("panel_button_label", "🎫 Open Ticket"),
            style=discord.ButtonStyle.blurple,
            custom_id=TICKET_OPEN_CID
        )
        btn.callback = self.open_cb
        self.add_item(btn)

    async def open_cb(self, interaction: discord.Interaction):
        await self.cog._create_ticket(interaction)


class ManagementView(View):
    def __init__(self, cog, ticket_id, opener_id):
        super().__init__(timeout=None)
        self.cog       = cog
        self.ticket_id = ticket_id
        self.opener_id = opener_id
        self.add_item(CloseConfirmButton(cog, ticket_id, opener_id))


# ------------------------
# TICKET COG
# ------------------------

class Ticket(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot            = bot
        self.config_manager = ConfigManager("config.json")
        self.config         = self.config_manager.load_config().get("ticket", {})
        self.db             = TicketDB()
        self.admin_roles    = set(self.config.get("staff_roles", []))

        # Re-attach persistent views for already-open tickets
        for ticket in self.db.get_all_open_tickets():
            self.bot.add_view(ManagementView(self, ticket["ticket_id"], ticket["owner_id"]))

    async def check_staff(self, interaction: discord.Interaction):
        user_roles = {str(r.id) for r in interaction.user.roles}
        return bool(user_roles.intersection(self.admin_roles)) or interaction.user.guild_permissions.administrator

    # ------------------------
    # TICKET CREATION
    # ------------------------

    async def _create_ticket(self, interaction: discord.Interaction):
        existing = self.db.get_user_open_ticket(interaction.guild.id, interaction.user.id)
        if existing:
            return await interaction.response.send_message("You already have an open ticket.", ephemeral=True)

        category = discord.utils.get(interaction.guild.categories, id=self.config.get("category_id"))
        if not category:
            return await interaction.response.send_message("Ticket category not configured.", ephemeral=True)

        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.display_name}",
            category=category,
            reason=f"Ticket opened by {interaction.user}"
        )
        await channel.set_permissions(interaction.guild.default_role, read_messages=False)
        await channel.set_permissions(interaction.user, read_messages=True, send_messages=True)
        for rid in self.admin_roles:
            role = interaction.guild.get_role(int(rid))
            if role:
                await channel.set_permissions(role, read_messages=True, send_messages=True)

        ticket_id = self.db.create_ticket(interaction.guild.id, channel.id, interaction.user.id)

        embed = discord.Embed(
            title=self.config.get("ticket_embed_title", "Support Ticket"),
            description=self.config.get("ticket_embed_desc", "Please describe your issue."),
            color=discord.Color.blue()
        )
        view = ManagementView(self, ticket_id, interaction.user.id)
        await channel.send(embed=embed, view=view)
        self.bot.add_view(view)

        await interaction.response.send_message(f"✅ Ticket created: {channel.mention}", ephemeral=True)

    @app_commands.command(name="ticket", description="Create a new support ticket.")
    async def ticket_cmd(self, interaction: discord.Interaction):
        await self._create_ticket(interaction)

    @app_commands.command(name="ticket_button", description="Post the ticket panel embed.")
    async def ticket_button_cmd(self, interaction: discord.Interaction):
        panel_ch = interaction.guild.get_channel(self.config.get("panel_channel_id"))
        if not panel_ch:
            return await interaction.response.send_message("Panel channel not found.", ephemeral=True)

        embed = discord.Embed(
            title=self.config.get("panel_embed_title", "Open a Ticket"),
            description=self.config.get("panel_embed_description", "Click below to open a ticket."),
            color=discord.Color.green()
        )
        view = OpenTicketView(self)
        await panel_ch.send(embed=embed, view=view)
        await interaction.response.send_message(f"✅ Panel posted in {panel_ch.mention}", ephemeral=True)

    # ------------------------
    # ADD / REMOVE MEMBERS
    # ------------------------

    async def ticket_add(self, interaction: discord.Interaction):
        ticket = self.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket or (interaction.user.id != ticket["owner_id"] and not await self.check_staff(interaction)):
            return await interaction.response.send_message("You cannot add members to this ticket.", ephemeral=True)

        msg = await interaction.response.send_message(
            "Reply to this message and mention the user to **add** them.", ephemeral=True
        )

        def check(m: discord.Message):
            return (
                m.author.id == interaction.user.id
                and m.reference
                and m.reference.message_id == msg.id
                and len(m.mentions) > 0
            )

        try:
            reply_msg = await self.bot.wait_for("message", check=check, timeout=60)
        except asyncio.TimeoutError:
            return await interaction.followup.send("No response received. Operation cancelled.", ephemeral=True)

        member = reply_msg.mentions[0]
        await interaction.channel.set_permissions(member, read_messages=True, send_messages=True)
        self.db.add_member(ticket["ticket_id"], member.id)
        await interaction.followup.send(f"✅ {member.mention} added to the ticket.", ephemeral=True)

    async def ticket_remove(self, interaction: discord.Interaction):
        ticket = self.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket or (interaction.user.id != ticket["owner_id"] and not await self.check_staff(interaction)):
            return await interaction.response.send_message("You cannot remove members from this ticket.", ephemeral=True)

        msg = await interaction.response.send_message(
            "Reply to this message and mention the user to **remove** them.", ephemeral=True
        )

        def check(m: discord.Message):
            return (
                m.author.id == interaction.user.id
                and m.reference
                and m.reference.message_id == msg.id
                and len(m.mentions) > 0
            )

        try:
            reply_msg = await self.bot.wait_for("message", check=check, timeout=60)
        except asyncio.TimeoutError:
            return await interaction.followup.send("No response received. Operation cancelled.", ephemeral=True)

        member = reply_msg.mentions[0]
        await interaction.channel.set_permissions(member, overwrite=None)
        self.db.remove_member(ticket["ticket_id"], member.id)
        await interaction.followup.send(f"✅ {member.mention} removed from the ticket.", ephemeral=True)

    # ------------------------
    # FORCE CLOSE (ADMIN)
    # ------------------------

    @app_commands.command(name="ticket_forceclose", description="Force close a ticket (Admin only).")
    async def ticket_forceclose_cmd(self, interaction: discord.Interaction):
        if not await self.check_staff(interaction):
            return await interaction.response.send_message("You cannot force-close tickets.", ephemeral=True)

        ticket = self.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message("This channel is not a ticket.", ephemeral=True)

        await interaction.channel.delete(reason=f"Ticket force-closed by {interaction.user}")
        self.db.close_ticket(ticket["ticket_id"])
        await interaction.response.send_message("Ticket force-closed.", ephemeral=True)


# ------------------------
# SETUP
# ------------------------

async def setup(bot: commands.Bot):
    await bot.add_cog(Ticket(bot))