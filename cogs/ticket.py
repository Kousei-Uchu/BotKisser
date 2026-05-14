import discord
from discord.ext import commands
from discord import app_commands
from discord.ui import View, Button
from typing import List

from utils.config_manager import ConfigManager
from utils.db_handlers.ticket_db import TicketDB

TICKET_OPEN_CID = "ticket:open_ticket"


# ------------------------
# BUTTONS & VIEWS
# ------------------------

class CloseConfirmButton(Button):
    def __init__(self, cog, ticket_id: int, opener_id: int):
        super().__init__(label="Confirm Close", style=discord.ButtonStyle.red)
        self.cog = cog
        self.ticket_id = ticket_id
        self.opener_id = opener_id

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.opener_id:
            return await interaction.response.send_message(
                "Only the ticket opener can confirm closing.",
                ephemeral=True
            )

        ticket = self.cog.db.get_ticket_by_id(self.ticket_id)
        if not ticket:
            return await interaction.response.send_message(
                "Ticket not found or already closed.",
                ephemeral=True
            )

        self.cog.db.close_ticket(self.ticket_id)
        await interaction.channel.delete(reason="Ticket closed")
        await interaction.response.send_message("Ticket closed.", ephemeral=True)


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
        self.add_item(CloseConfirmButton(cog, ticket_id, opener_id))


# ------------------------
# COG
# ------------------------

class Ticket(commands.Cog):
    def __init__(self, bot: commands.Bot):
        self.bot = bot
        self.config_manager = ConfigManager("config.json")
        self.config = self.config_manager.load_config().get("ticket", {})
        self.db = TicketDB()

        self.admin_roles = set(self.config.get("staff_roles", []))

        # persistent views (IMPORTANT)
        self.bot.add_view(OpenTicketView(self))

        for ticket in self.db.get_all_open_tickets():
            self.bot.add_view(
                ManagementView(self, ticket["ticket_id"], ticket["owner_id"])
            )

    # ------------------------
    # STAFF CHECK
    # ------------------------

    async def check_staff(self, interaction: discord.Interaction):
        user_roles = {str(r.id) for r in interaction.user.roles}
        return bool(user_roles.intersection(self.admin_roles)) or interaction.user.guild_permissions.administrator

    # ------------------------
    # CREATE TICKET
    # ------------------------

    async def _create_ticket(self, interaction: discord.Interaction):
        is_staff = await self.check_staff(interaction)

        if not is_staff:
            existing = self.db.get_user_open_ticket(
                interaction.guild.id,
                interaction.user.id
            )
            if existing:
                return await interaction.response.send_message(
                    "You already have an open ticket.",
                    ephemeral=True
                )

        category = discord.utils.get(
            interaction.guild.categories,
            id=self.config.get("category_id")
        )

        if not category:
            return await interaction.response.send_message(
                "Ticket category not configured.",
                ephemeral=True
            )

        channel = await interaction.guild.create_text_channel(
            name=f"ticket-{interaction.user.display_name}",
            category=category
        )

        await channel.set_permissions(interaction.guild.default_role, read_messages=False)
        await channel.set_permissions(interaction.user, read_messages=True, send_messages=True)

        for rid in self.admin_roles:
            role = interaction.guild.get_role(int(rid))
            if role:
                await channel.set_permissions(role, read_messages=True, send_messages=True)

        ticket_id = self.db.create_ticket(
            interaction.guild.id,
            channel.id,
            interaction.user.id
        )

        embed = discord.Embed(
            title="Support Ticket",
            description="Describe your issue.",
            color=discord.Color.blue()
        )

        await channel.send(embed=embed, view=ManagementView(self, ticket_id, interaction.user.id))

        await interaction.response.send_message(
            f"Ticket created: {channel.mention}",
            ephemeral=True
        )

    # ------------------------
    # COMMANDS
    # ------------------------

    @app_commands.command(name="ticket", description="Create a ticket")
    async def ticket_cmd(self, interaction: discord.Interaction):
        await self._create_ticket(interaction)

    @app_commands.command(name="ticket_button", description="Post ticket panel")
    async def ticket_button_cmd(self, interaction: discord.Interaction):
        panel = interaction.guild.get_channel(self.config.get("panel_channel_id"))

        if not panel:
            return await interaction.response.send_message(
                "Panel channel not found.",
                ephemeral=True
            )

        embed = discord.Embed(
            title="Open a Ticket",
            description="Click below to open a ticket.",
            color=discord.Color.green()
        )

        await panel.send(embed=embed, view=OpenTicketView(self))

        await interaction.response.send_message("Panel posted.", ephemeral=True)

    # ------------------------
    # ADD MEMBERS (MULTI)
    # ------------------------

    @app_commands.command(name="ticket_add", description="Add members to ticket")
    @app_commands.describe(members="Members to add")
    async def ticket_add(
        self,
        interaction: discord.Interaction,
        members: List[discord.Member]
    ):
        ticket = self.db.get_ticket_by_channel(interaction.channel.id)

        if not ticket:
            return await interaction.response.send_message(
                "Not a ticket channel.",
                ephemeral=True
            )

        if interaction.user.id != ticket["owner_id"] and not await self.check_staff(interaction):
            return await interaction.response.send_message(
                "No permission.",
                ephemeral=True
            )

        added = []

        for m in members:
            await interaction.channel.set_permissions(
                m,
                read_messages=True,
                send_messages=True
            )
            self.db.add_member(ticket["ticket_id"], m.id)
            added.append(m.mention)

        await interaction.response.send_message(
            f"Added: {', '.join(added)}",
            ephemeral=True
        )

    # ------------------------
    # REMOVE MEMBERS (MULTI)
    # ------------------------

    @app_commands.command(name="ticket_remove", description="Remove members from ticket")
    @app_commands.describe(members="Members to remove")
    async def ticket_remove(
        self,
        interaction: discord.Interaction,
        members: List[discord.Member]
    ):
        ticket = self.db.get_ticket_by_channel(interaction.channel.id)

        if not ticket:
            return await interaction.response.send_message(
                "Not a ticket channel.",
                ephemeral=True
            )

        if interaction.user.id != ticket["owner_id"] and not await self.check_staff(interaction):
            return await interaction.response.send_message(
                "No permission.",
                ephemeral=True
            )

        removed = []

        for m in members:
            await interaction.channel.set_permissions(m, overwrite=None)
            self.db.remove_member(ticket["ticket_id"], m.id)
            removed.append(m.mention)

        await interaction.response.send_message(
            f"Removed: {', '.join(removed)}",
            ephemeral=True
        )

    # ------------------------
    # REQUEST CLOSE
    # ------------------------

    @app_commands.command(name="requestclose", description="Request ticket close (staff)")
    async def requestclose(self, interaction: discord.Interaction):

        if not await self.check_staff(interaction):
            return await interaction.response.send_message(
                "Staff only.",
                ephemeral=True
            )

        ticket = self.db.get_ticket_by_channel(interaction.channel.id)
        if not ticket:
            return await interaction.response.send_message(
                "Not a ticket.",
                ephemeral=True
            )

        owner = interaction.guild.get_member(ticket["owner_id"])

        embed = discord.Embed(
            title="Close Request",
            description=f"Hey {owner.mention}! Are you ready for me to close this ticket?",
            color=discord.Color.orange()
        )

        await interaction.channel.send(
            content=owner.mention,
            embed=embed,
            view=CloseConfirmButton(self, ticket["ticket_id"], ticket["owner_id"])
        )

        await interaction.response.send_message("Request sent.", ephemeral=True)


# ------------------------
# SETUP
# ------------------------

async def setup(bot: commands.Bot):
    await bot.add_cog(Ticket(bot))